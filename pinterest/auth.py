"""Authentication blueprint: register, login, logout."""
from flask import (Blueprint, current_app, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import generate_password_hash

from .extensions import db
from .models import pin_category, users
from .utils import display_name, verify_password

bp = Blueprint("auth", __name__)


@bp.route('/register', methods=["GET", "POST"])
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
    return redirect(url_for("main.profile"))


@bp.route('/login', methods=["GET", "POST"])
def login():
    nm = display_name()

    if request.method == "GET":
        return render_template("signin.html", display_nm=nm)

    email = (request.form.get("email") or "").strip().lower()
    pwd = request.form.get("pwd") or ""

    # Dedicated admin login (credentials configurable via environment)
    if (email == current_app.config["ADMIN_EMAIL"]
            and pwd == current_app.config["ADMIN_PASSWORD"]):
        session["email"] = current_app.config["ADMIN_EMAIL"]
        session["username"] = "Admin"
        return redirect(url_for("main.index"))

    # Case-insensitive lookup so accounts registered before emails were
    # normalised to lowercase can still sign in
    record = users.query.filter(db.func.lower(users.email) == email).first()
    if record is not None and verify_password(record, pwd):
        session["username"] = record.name
        session["email"] = record.email  # keep the stored casing in session
        return redirect(url_for("main.index"))

    return render_template("signin.html", display_nm=nm,
                           error="Wrong email or Password entered!")


@bp.route('/logout')
def logout():
    session.pop("username", None)
    session.pop("email", None)
    return redirect(url_for("main.index"))
