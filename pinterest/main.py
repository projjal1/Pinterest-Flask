"""Main blueprint: feed, search, pins, profiles, follows."""
import os
import random
from datetime import datetime

from flask import (Blueprint, current_app, redirect, render_template, request,
                   send_from_directory, session, url_for)

from .extensions import db
from .models import (admin_post, follow_user, images, pin_category,
                     saved_pins, track_visits, user_slugs, users)
from .recommender import recommended_images, schedule_similarity_refresh
from .utils import (current_user, display_name, login_required, normalize_url,
                    open_image_upload)

bp = Blueprint("main", __name__)


# Pins served per page of the lazily-loaded feed
PAGE_SIZE = 24


def _feed_records(category):
    """Full ordered record list for a feed variant (small catalogue, so
    slicing an in-memory list keeps the seeded shuffle simple)."""
    if category == "All" and "email" not in session:
        return images.query.all()
    if category == "All" and "email" in session:
        if session["username"] != "Admin":
            # Personalised feed, falling back to everything for new users
            return recommended_images(session["email"]) or images.query.all()
        return images.query.all()[-5:]
    return images.query.filter_by(fields=category).all()


def _search_records(query):
    like = f"%{query}%"
    return images.query.filter(
        db.or_(images.title.ilike(like),
               images.fields.ilike(like),
               images.description.ilike(like))).all()


def _paginate(records, page):
    start = (page - 1) * PAGE_SIZE
    return records[start:start + PAGE_SIZE], start + PAGE_SIZE < len(records)


@bp.route('/', defaults={'category': "All"})
@bp.route('/<category>')
def index(category="All"):
    # A per-visit seed keeps the shuffle stable across subsequent
    # /api/pins page requests, so no pin repeats or goes missing
    seed = request.args.get('seed', type=int) or random.randrange(1_000_000)
    record_images = _feed_records(category)
    random.Random(seed).shuffle(record_images)
    page_items, has_more = _paginate(record_images, 1)

    return render_template("home.html", display_nm=display_name(),
                           images_list=page_items, has_more=has_more,
                           feed_seed=seed, feed_category=category)


@bp.route('/search')
def search():
    query = (request.args.get('q') or "").strip()
    results = _search_records(query) if query else []
    page_items, has_more = _paginate(results, 1)
    return render_template("home.html", display_nm=display_name(),
                           images_list=page_items, has_more=has_more,
                           search_query=query, feed_seed=0)


@bp.route('/api/pins')
def api_pins():
    """Next page of feed cards for the infinite scroller, as an HTML
    fragment plus a has_more flag."""
    page = max(request.args.get('page', 1, type=int), 1)
    seed = request.args.get('seed', 0, type=int)
    query = (request.args.get('q') or "").strip()
    category = request.args.get('category') or "All"

    if query:
        records = _search_records(query)
    else:
        records = _feed_records(category)
        random.Random(seed).shuffle(records)

    page_items, has_more = _paginate(records, page)
    html = render_template("_pin_cards.html", images_list=page_items)
    return {"html": html, "has_more": has_more}


@bp.route('/today')
def exclusive():
    listing_images = admin_post.query.order_by(admin_post.id.desc()).all()
    return render_template("latest_uploaded.html", display_nm=display_name(),
                           images_list=listing_images)


@bp.route('/follow/<email>', methods=["POST"])
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

    return redirect(url_for('main.profile_view', profile_email=email, action=1))


# Save pins
@bp.route('/save_pins/<int:img_id>')
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

    return redirect(url_for('main.view_photo', photo_id=img_id))


@bp.route('/view/<int:photo_id>', methods=["POST", "GET"])
def view_photo(photo_id):
    img_data = images.query.filter_by(id=photo_id).first_or_404()

    if request.method == "POST":
        # Download the original image file
        return send_from_directory(current_app.config["PORTAL_IMAGE_DIR"],
                                   img_data.filename or f"{photo_id}.jpg",
                                   as_attachment=True)

    user_details = img_data.author or users.query.filter_by(
        id=img_data.user_id).first_or_404()

    nm = display_name()
    if "username" in session and nm != "Admin":
        # Track visit for the recommendation engine
        visitor = current_user()
        if visitor is not None:
            db.session.add(track_visits(user_id=visitor.id, img_id=photo_id))
            db.session.commit()

    # "More like this": other pins from the same category
    img_obj = [rec for rec in images.query.filter_by(fields=img_data.fields)
               if rec.id != img_data.id]
    random.shuffle(img_obj)

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
                           follow_count=user_details.follower_count,
                           flag_follow_check=flag_follow,
                           flag_save_check=flag_save)


@bp.route('/author', methods=["GET", "POST"])
@login_required
def profile():
    nm = session["username"]

    if request.method == "GET":
        return render_template("profile.html", display_nm=nm)

    bio = request.form.get("bio")
    website = normalize_url(request.form.get("url"))

    user_obj = current_user()
    if user_obj is None:
        return redirect(url_for('auth.logout'))

    # Profile picture is optional
    read_img = open_image_upload(request.files.get("img"))
    if read_img is not None:
        read_img.save(os.path.join(current_app.config["PORTAL_IMAGE_DIR"],
                                   f"user{user_obj.id}.jpg"))

    # Create the slug record, or update it if the user already has one
    if user_obj.slug is None:
        db.session.add(user_slugs(user_id=user_obj.id, bio=bio,
                                  website=website))
    else:
        user_obj.slug.bio = bio
        user_obj.slug.website = website
    db.session.commit()

    schedule_similarity_refresh()
    return redirect(url_for('main.index'))


# Action 0 means plain login prompt, 1 means "log in to view this profile"
@bp.route('/profile', defaults={'profile_email': "Default", "action": "0"})
@bp.route('/profile/<profile_email>/<action>')
def profile_view(profile_email, action):
    if "username" not in session:
        if str(action) == "0":
            return render_template("sign.html", display_nm="Author")
        return render_template("sign.html", display_nm="Author",
                               error="You need to log in to view profile of users.")
    if session["username"] == "Admin":
        return redirect(url_for('main.index'))

    nm = session["username"]
    email = session["email"] if profile_email == "Default" else profile_email

    obj = users.query.filter_by(email=email).first_or_404()
    img_obj = list(obj.pins)
    len_posts = len(img_obj)

    # Show saved pins alongside their own uploads on the user's own profile
    if email == session["email"]:
        for each in obj.saved:
            if each.image is not None and each.image not in img_obj:
                img_obj.append(each.image)

    return render_template("profile_view.html", display_nm=nm, user_data=obj,
                           slug_data=obj.slug, images_list=img_obj,
                           img_count=len_posts,
                           follow_count=obj.follower_count,
                           following_count=obj.following_count)


@bp.route('/post', methods=["GET", "POST"])
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
        return redirect(url_for('auth.logout'))

    image_obj = images(title=title, description=desc, fields=field,
                       links=links, user_id=user_obj.id)
    db.session.add(image_obj)
    db.session.commit()

    image_obj.filename = f"{image_obj.id}.jpg"
    db.session.commit()
    image.save(os.path.join(current_app.config["PORTAL_IMAGE_DIR"],
                            image_obj.filename))

    schedule_similarity_refresh()
    return render_template("post.html", display_nm=nm, success="Image Saved",
                           categories=cat_records)
