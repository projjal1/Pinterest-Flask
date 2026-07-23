"""Pinterest clone built with Flask.

Image pins, user profiles, follows, saved pins and a collaborative-filtering
recommendation engine (TruncatedSVD over user/interest/visit data).
"""
import os
import pickle
import random
from collections import Counter
from datetime import datetime
from functools import wraps
from urllib.parse import urlparse

import numpy as np
import pandas as pd
from flask import (Flask, abort, redirect, render_template, request,
                   send_from_directory, session, url_for)
from flask_sqlalchemy import SQLAlchemy
from PIL import Image, UnidentifiedImageError
from sklearn.decomposition import TruncatedSVD
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORTAL_IMAGE_DIR = os.path.join(BASE_DIR, "static", "portal_images")
ADMIN_PROMO_DIR = os.path.join(BASE_DIR, "static", "admin_promo")
DATA_MINING_DIR = os.path.join(BASE_DIR, "data-mining")

# Flask app configs
app = Flask(__name__)
# Absolute path so the bundled DB keeps working with Flask-SQLAlchemy 3.x,
# which resolves relative sqlite paths against the instance/ folder.
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "user-data.sqlite3"))
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB upload limit

# Admin credentials — override in production via environment variables
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "administrator@pinterest.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")

# Database
db = SQLAlchemy(app)


class users(db.Model):
    id = db.Column('user_id', db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100))
    password = db.Column(db.String(255))  # stores a salted hash, not plaintext
    interests = db.Column(db.String(200))


class images(db.Model):
    id = db.Column('image_id', db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    fields = db.Column(db.String(300))
    description = db.Column(db.String(1000))
    links = db.Column(db.String(200))
    user_id = db.Column(db.Integer)


class user_slugs(db.Model):
    id = db.Column('slug_id', db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    bio = db.Column(db.String(1000))
    website = db.Column(db.String(100))


class pin_category(db.Model):
    id = db.Column('category_id', db.Integer, primary_key=True)
    name = db.Column(db.String(200))


class track_visits(db.Model):
    id = db.Column('visit_id', db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    img_id = db.Column(db.Integer)


class admin_post(db.Model):
    id = db.Column('admin_id', db.Integer, primary_key=True)
    advertisement_title = db.Column(db.String(100))
    thought_title = db.Column(db.String(100))
    advertisement_link = db.Column(db.String(100))
    thought_link = db.Column(db.String(100))
    date = db.Column(db.String(100))


class follow_user(db.Model):
    id = db.Column('follow_id', db.Integer, primary_key=True)
    user_email = db.Column(db.String(100))
    follower_email = db.Column(db.String(100))


class saved_pins(db.Model):
    id = db.Column('save_id', db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    img_id = db.Column(db.Integer)


# Create tables on first run (no-op if they already exist)
with app.app_context():
    db.create_all()


# ------------------------------------------------------------------ helpers
@app.context_processor
def inject_year():
    """Footer copyright year for base.html."""
    return {"year": datetime.now().year}


def display_name():
    return session.get("username", "Author")


def current_user():
    if "email" not in session:
        return None
    return users.query.filter_by(email=session["email"]).first()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "username" not in session:
            return render_template("sign.html", display_nm="Author",
                                   error="You need to log in first.")
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("username") != "Admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def normalize_url(link):
    """Prefix a scheme when missing instead of blindly concatenating."""
    link = (link or "").strip()
    if link and not urlparse(link).scheme:
        link = "https://" + link
    return link


def open_image_upload(file_storage):
    """Return a JPEG-safe PIL image from an upload, or None if invalid."""
    if file_storage is None or file_storage.filename == "":
        return None
    try:
        img = Image.open(file_storage)
        return img.convert("RGB")  # PNG/RGBA/palette uploads save fine as JPEG
    except (UnidentifiedImageError, OSError):
        return None


def verify_password(user, pwd):
    """Check a password hash; transparently upgrade legacy plaintext rows."""
    stored = user.password or ""
    if stored.startswith(("pbkdf2:", "scrypt:")):
        return check_password_hash(stored, pwd)
    if stored and stored == pwd:  # account created before hashing existed
        user.password = generate_password_hash(pwd)
        db.session.commit()
        return True
    return False


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

    os.makedirs(DATA_MINING_DIR, exist_ok=True)
    with open(os.path.join(DATA_MINING_DIR, 'user-corr.pkl'), 'wb') as file:
        pickle.dump(corr_mat, file)
    with open(os.path.join(DATA_MINING_DIR, 'track_data.pkl'), 'wb') as file:
        pickle.dump(track_user_images, file)
    with open(os.path.join(DATA_MINING_DIR, 'final_set.pkl'), 'wb') as file:
        pickle.dump(final_set, file)
    return True


def refresh_similarity():
    """Recompute recommendations, but never let it break a user request."""
    try:
        compute_user_similarity()
    except Exception as exc:  # small-data edge cases shouldn't 500 the app
        app.logger.warning("Similarity recompute skipped: %s", exc)


# Images picked through user-user collaborative filtering
def recommended_images(email):
    try:
        with open(os.path.join(DATA_MINING_DIR, 'final_set.pkl'), 'rb') as file:
            final_set = pickle.load(file)
        with open(os.path.join(DATA_MINING_DIR, 'user-corr.pkl'), 'rb') as file:
            corr_mat = pickle.load(file)
        with open(os.path.join(DATA_MINING_DIR, 'track_data.pkl'), 'rb') as file:
            track_user_images = pickle.load(file)
        user_list = list(final_set.index)
        idx = user_list.index(email)
    except ValueError:
        return []  # user not in the matrix yet
    except Exception as exc:
        # Missing or stale pickles (e.g. written by an older pandas) must
        # never take down the home feed — fall back to the generic feed
        app.logger.warning("Recommendation model unavailable: %s", exc)
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


# ------------------------------------------------------------------- routes
# Admin post
@app.route("/admin_post", methods=["GET", "POST"])
@admin_required
def admin_listing():
    if request.method == "GET":
        return render_template("admin_post.html", display_nm="Admin")

    advertisement_title = request.form.get('iname2')
    advertisement_link = normalize_url(request.form.get('link2'))
    thought_title = request.form.get('iname1')
    thought_link = normalize_url(request.form.get('link1'))

    # Validate both uploads before touching the database
    img_adv = open_image_upload(request.files.get('img2'))
    img_thought = open_image_upload(request.files.get('img1'))
    if img_adv is None or img_thought is None:
        return render_template("admin_post.html", display_nm="Admin",
                               error="Both uploads must be valid image files.")

    admin_obj = admin_post(advertisement_link=advertisement_link,
                           advertisement_title=advertisement_title,
                           thought_title=thought_title,
                           thought_link=thought_link,
                           date=datetime.now().strftime("%d %B, %Y"))
    db.session.add(admin_obj)
    db.session.commit()

    img_adv.save(os.path.join(ADMIN_PROMO_DIR, f"adv{admin_obj.id}.jpg"))
    img_thought.save(os.path.join(ADMIN_PROMO_DIR, f"thought{admin_obj.id}.jpg"))

    return redirect(url_for('index'))


# Routing functions
@app.route('/', defaults={'category': "All"})
@app.route('/<category>')
def index(category="All"):
    if category == "All" and "email" not in session:
        record_images = images.query.all()
    elif category == "All" and "email" in session:
        if session["username"] != "Admin":
            # Personalised feed, falling back to everything for new users
            record_images = recommended_images(session["email"]) or images.query.all()
        else:
            record_images = images.query.all()[-5:]
    else:
        record_images = images.query.filter_by(fields=category).all()

    random.shuffle(record_images)
    return render_template("home.html", display_nm=display_name(),
                           images_list=record_images)


@app.route('/follow/<email>', methods=["POST"])
def user_follow_action(email):
    if "username" not in session:
        return render_template("sign.html", display_nm="Author",
                               error="You need to log in to follow users.")

    u_email = session["email"]
    already = follow_user.query.filter_by(user_email=email,
                                          follower_email=u_email).first()
    if u_email != email and already is None:
        db.session.add(follow_user(user_email=email, follower_email=u_email))
        db.session.commit()

    return redirect(url_for('profile_view', profile_email=email, action=1))


@app.route('/today')
def exclusive():
    listing_images = admin_post.query.all()[::-1]
    return render_template("latest_uploaded.html", display_nm=display_name(),
                           images_list=listing_images)


# Save pins
@app.route('/save_pins/<int:img_id>')
def save_pins(img_id):
    if "username" not in session:
        return render_template("sign.html", display_nm="Author",
                               error="You need to log in to save images.")

    user_rec = current_user()
    if user_rec is not None:
        already = saved_pins.query.filter_by(user_id=user_rec.id,
                                             img_id=img_id).first()
        if already is None:
            db.session.add(saved_pins(user_id=user_rec.id, img_id=img_id))
            db.session.commit()

    return redirect(url_for('view_photo', photo_id=img_id))


@app.route('/view/<int:photo_id>', methods=["POST", "GET"])
def view_photo(photo_id):
    if request.method == "POST":
        # Download the original image file
        return send_from_directory(PORTAL_IMAGE_DIR, f"{photo_id}.jpg",
                                   as_attachment=True)

    img_data = images.query.filter_by(id=photo_id).first_or_404()
    user_details = users.query.filter_by(id=img_data.user_id).first_or_404()

    nm = display_name()
    if "username" in session and nm != "Admin":
        # Track visit for the recommendation engine
        visitor = current_user()
        if visitor is not None:
            db.session.add(track_visits(user_id=visitor.id, img_id=photo_id))
            db.session.commit()

    # "More like this": other pins from the same category
    img_obj = images.query.filter_by(fields=img_data.fields).all()
    img_obj = [rec for rec in img_obj if rec.id != img_data.id]
    random.shuffle(img_obj)
    follow_count = follow_user.query.filter_by(
        user_email=user_details.email).count()

    flag_follow, flag_save = 1, 1
    if "username" in session:
        viewer = current_user()
        if session["email"] == user_details.email:
            flag_follow = 0
        elif follow_user.query.filter_by(user_email=user_details.email,
                                         follower_email=session["email"]).first():
            flag_follow = 0
        if viewer is not None and saved_pins.query.filter_by(
                user_id=viewer.id, img_id=photo_id).first():
            flag_save = 0

    return render_template("view-photo.html", display_nm=nm, img_data=img_data,
                           user_data=user_details, images_list=img_obj[:20],
                           follow_count=follow_count,
                           flag_follow_check=flag_follow,
                           flag_save_check=flag_save)


@app.route('/author', methods=["GET", "POST"])
@login_required
def profile():
    nm = session["username"]

    if request.method == "GET":
        return render_template("profile.html", display_nm=nm)

    bio = request.form.get("bio")
    website = normalize_url(request.form.get("url"))

    user_obj = current_user()
    if user_obj is None:
        return redirect(url_for('logout'))

    # Profile picture is optional
    read_img = open_image_upload(request.files.get("img"))
    if read_img is not None:
        read_img.save(os.path.join(PORTAL_IMAGE_DIR, f"user{user_obj.id}.jpg"))

    # Create the slug record, or update it if the user already has one
    slug = user_slugs.query.filter_by(user_id=user_obj.id).first()
    if slug is None:
        db.session.add(user_slugs(user_id=user_obj.id, bio=bio, website=website))
    else:
        slug.bio = bio
        slug.website = website
    db.session.commit()

    refresh_similarity()
    return redirect(url_for('index'))


# Action 0 means plain login prompt, 1 means "log in to view this profile"
@app.route('/profile', defaults={'profile_email': "Default", "action": "0"})
@app.route('/profile/<profile_email>/<action>')
def profile_view(profile_email, action):
    if "username" not in session:
        if str(action) == "0":
            return render_template("sign.html", display_nm="Author")
        return render_template("sign.html", display_nm="Author",
                               error="You need to log in to view profile of users.")
    if session["username"] == "Admin":
        return redirect(url_for('index'))

    nm = session["username"]
    email = session["email"] if profile_email == "Default" else profile_email

    obj = users.query.filter_by(email=email).first_or_404()
    slug_obj = user_slugs.query.filter_by(user_id=obj.id).first()
    img_obj = images.query.filter_by(user_id=obj.id).all()
    len_posts = len(img_obj)

    # Show saved pins alongside their own uploads on the user's own profile
    if email == session["email"]:
        for each in saved_pins.query.filter_by(user_id=obj.id).all():
            rec = db.session.get(images, each.img_id)
            if rec is not None and rec not in img_obj:
                img_obj.append(rec)

    follow_count = follow_user.query.filter_by(user_email=email).count()
    following_count = follow_user.query.filter_by(follower_email=email).count()

    return render_template("profile_view.html", display_nm=nm, user_data=obj,
                           slug_data=slug_obj, images_list=img_obj,
                           img_count=len_posts, follow_count=follow_count,
                           following_count=following_count)


@app.route('/post', methods=["GET", "POST"])
@login_required
def post():
    nm = session["username"]
    cat_records = pin_category.query.all()

    if request.method == "GET":
        return render_template("post.html", display_nm=nm,
                               categories=cat_records)

    title = request.form.get("iname")
    desc = request.form.get("desc")
    field = request.form.get("cat")
    links = normalize_url(request.form.get("links"))

    # Validate the upload before creating the database record
    image = open_image_upload(request.files.get("img"))
    if image is None:
        return render_template("post.html", display_nm=nm,
                               error="Please choose a valid image file.",
                               categories=cat_records)

    user_obj = current_user()
    if user_obj is None:
        return redirect(url_for('logout'))

    image_obj = images(title=title, description=desc, fields=field,
                       links=links, user_id=user_obj.id)
    db.session.add(image_obj)
    db.session.commit()

    image.save(os.path.join(PORTAL_IMAGE_DIR, f"{image_obj.id}.jpg"))

    refresh_similarity()
    return render_template("post.html", display_nm=nm, success="Image Saved",
                           categories=cat_records)


@app.route('/logout')
def logout():
    session.pop("username", None)
    session.pop("email", None)
    return redirect(url_for("index"))


@app.route('/register', methods=["GET", "POST"])
def register():
    nm = display_name()
    cat_records = pin_category.query.all()

    if request.method == "GET":
        return render_template("signup.html", display_nm=nm,
                               categories=cat_records)

    fname = (request.form.get("fname") or "").strip()
    lname = (request.form.get("lname") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    pwd = request.form.get("pwd") or ""
    interest_list = request.form.getlist("int")

    if not (fname and email and pwd):
        return render_template("signup.html", display_nm=nm,
                               error="Name, email and password are required.",
                               categories=cat_records)

    if users.query.filter(db.func.lower(users.email) == email).first() is not None:
        return render_template("signup.html", display_nm=nm,
                               error="An account with that email already exists.",
                               categories=cat_records)

    full_name = f"{fname} {lname}".strip()
    user_obj = users(name=full_name, email=email,
                     password=generate_password_hash(pwd),
                     interests=",".join(interest_list))
    db.session.add(user_obj)
    db.session.commit()

    session["username"] = full_name
    session["email"] = email
    return redirect(url_for("profile"))


@app.route('/login', methods=["GET", "POST"])
def login():
    nm = display_name()

    if request.method == "GET":
        return render_template("signin.html", display_nm=nm)

    email = (request.form.get("email") or "").strip().lower()
    pwd = request.form.get("pwd") or ""

    # Dedicated admin login (credentials configurable via environment)
    if email == ADMIN_EMAIL and pwd == ADMIN_PASSWORD:
        session["email"] = ADMIN_EMAIL
        session["username"] = "Admin"
        return redirect(url_for("index"))

    # Case-insensitive lookup so accounts registered before emails were
    # normalised to lowercase can still sign in
    record = users.query.filter(db.func.lower(users.email) == email).first()
    if record is not None and verify_password(record, pwd):
        session["username"] = record.name
        session["email"] = record.email  # keep the stored casing in session
        return redirect(url_for("index"))

    return render_template("signin.html", display_nm=nm,
                           error="Wrong email or Password entered!")


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "1") == "1", port=8000)
