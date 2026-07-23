"""Collaborative-filtering recommendation engine.

User/interest/visit data is folded into a crosstab matrix, reduced with
TruncatedSVD and turned into a user-user similarity matrix. The heavy
recompute runs in a background thread so posting a pin stays fast.
"""
import os
import pickle
import threading
from collections import Counter

import numpy as np
import pandas as pd
from flask import current_app
from sklearn.decomposition import TruncatedSVD

from .extensions import db
from .models import images, pin_category, track_visits, users

# Only one recompute at a time; extra requests are dropped (the running
# recompute already reflects the latest committed data or will shortly)
_refresh_lock = threading.Lock()


def _pickle_path(name):
    return os.path.join(current_app.config["DATA_MINING_DIR"], name)


# ---------------------------------------------------------- data extractors
def extract_users():
    rows = []
    for rec in users.query.all():
        for interest in (rec.interests or "").split(","):
            interest = interest.strip()
            if interest:
                rows.append((rec.id, rec.email, interest))
    df = pd.DataFrame(rows, columns=["user_id", "name", "category"])
    df["flag"] = np.ones(len(df))
    return df


def extract_images():
    rows = [(rec.id, rec.title, rec.fields, rec.user_id)
            for rec in images.query.all()]
    df = pd.DataFrame(rows, columns=["img_id", "title", "category", "user_id"])
    df["img_flag"] = np.ones(len(df))
    return df


def extract_tracks():
    rows = [(rec.id, rec.user_id, rec.img_id)
            for rec in track_visits.query.all()]
    df = pd.DataFrame(rows, columns=["visit_id", "user_id", "img_id"])
    df["visits"] = np.ones(len(df))
    return df


def extract_category():
    rows = [(rec.id, rec.name) for rec in pin_category.query.all()]
    return pd.DataFrame(rows, columns=["cat_id", "category"])


# Compute the ratings crosstab matrix and user-user similarity scores
def compute_user_similarity():
    user_data = extract_users()
    image_data = extract_images()
    track_data = extract_tracks()
    category_data = extract_category()

    if user_data.empty or image_data.empty:
        return False

    user_merge_category = pd.merge(user_data[["name", "category", "flag"]],
                                   category_data[["category"]], on="category")
    user_category = user_merge_category.pivot_table(
        values='flag', index='name', columns='category', fill_value=0)
    combined_dataset = pd.merge(
        user_data[["user_id", "name"]],
        image_data[["img_id", "user_id", "category", "img_flag"]], on="user_id")
    user_images = combined_dataset.pivot_table(
        values='img_flag', index='name', columns='category', fill_value=0)
    track_images = pd.merge(image_data[['img_id', 'title']],
                            track_data[['img_id', 'user_id']], on="img_id")
    track_user_images = pd.merge(track_images, user_data[["user_id", "name"]],
                                 on="user_id")

    final_set = pd.merge(user_category, user_images, on="name")

    # TruncatedSVD needs fewer components than features and 2+ users
    n_components = min(5, final_set.shape[1] - 1, final_set.shape[0] - 1)
    if n_components < 1:
        return False

    svd = TruncatedSVD(n_components=n_components, random_state=17)
    resultant_matrix = svd.fit_transform(final_set)
    corr_mat = np.corrcoef(resultant_matrix)

    os.makedirs(current_app.config["DATA_MINING_DIR"], exist_ok=True)
    with open(_pickle_path('user-corr.pkl'), 'wb') as file:
        pickle.dump(corr_mat, file)
    with open(_pickle_path('track_data.pkl'), 'wb') as file:
        pickle.dump(track_user_images, file)
    with open(_pickle_path('final_set.pkl'), 'wb') as file:
        pickle.dump(final_set, file)
    return True


def schedule_similarity_refresh(app=None):
    """Recompute the model off the request path; never break the request."""
    app = app or current_app._get_current_object()

    if app.config.get("TESTING"):
        # Deterministic in tests: run synchronously
        try:
            with app.app_context():
                compute_user_similarity()
        except Exception as exc:
            app.logger.warning("Similarity recompute skipped: %s", exc)
        return

    def _worker():
        if not _refresh_lock.acquire(blocking=False):
            return  # a recompute is already in flight
        try:
            with app.app_context():
                compute_user_similarity()
        except Exception as exc:
            app.logger.warning("Similarity recompute skipped: %s", exc)
        finally:
            _refresh_lock.release()

    threading.Thread(target=_worker, name="similarity-refresh",
                     daemon=True).start()


# Images picked through user-user collaborative filtering
def recommended_images(email):
    try:
        with open(_pickle_path('final_set.pkl'), 'rb') as file:
            final_set = pickle.load(file)
        with open(_pickle_path('user-corr.pkl'), 'rb') as file:
            corr_mat = pickle.load(file)
        with open(_pickle_path('track_data.pkl'), 'rb') as file:
            track_user_images = pickle.load(file)
        user_list = list(final_set.index)
        idx = user_list.index(email)
    except ValueError:
        return []  # user not in the matrix yet
    except Exception as exc:
        # Missing or stale pickles (e.g. written by an older pandas) must
        # never take down the home feed — fall back to the generic feed
        current_app.logger.warning("Recommendation model unavailable: %s", exc)
        return []

    threshold = 0.3
    user_select = Counter()
    for itr, score in enumerate(corr_mat[idx]):
        if threshold <= score <= 0.98:  # skip self-matches and weak matches
            user_select[itr] = score

    common_users = 5  # change to pull pins from more similar users

    ids = []
    for k, _ in user_select.most_common(common_users):
        row = track_user_images[track_user_images["name"] == user_list[k]]
        for img_id in row.img_id.values:
            if img_id not in ids:
                ids.append(img_id)

    objs = (db.session.get(images, int(img_id)) for img_id in ids)
    return [obj for obj in objs if obj is not None]
