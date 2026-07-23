"""Shared helpers: auth guards, password handling, upload validation."""
from functools import wraps
from urllib.parse import urlparse

from flask import abort, render_template, session
from PIL import Image, UnidentifiedImageError
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db
from .models import users


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
