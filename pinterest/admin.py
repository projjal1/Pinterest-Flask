"""Admin blueprint: daily advertisement / thought-of-the-day posts."""
import os
from datetime import datetime

from flask import (Blueprint, current_app, redirect, render_template, request,
                   url_for)

from .extensions import db
from .models import admin_post
from .utils import admin_required, normalize_url, open_image_upload

bp = Blueprint("admin", __name__)


@bp.route("/admin_post", methods=["GET", "POST"])
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

    promo_dir = current_app.config["ADMIN_PROMO_DIR"]
    img_adv.save(os.path.join(promo_dir, f"adv{admin_obj.id}.jpg"))
    img_thought.save(os.path.join(promo_dir, f"thought{admin_obj.id}.jpg"))

    return redirect(url_for('main.index'))
