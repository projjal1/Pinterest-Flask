"""Pytest fixtures: app factory wired to a temporary database and dirs."""
import os
import sys

import pytest
from werkzeug.security import generate_password_hash

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pinterest import create_app  # noqa: E402
from pinterest.extensions import db  # noqa: E402
from pinterest.models import images, pin_category, users  # noqa: E402


def make_app(tmp_path, **overrides):
    portal = tmp_path / "portal_images"
    promo = tmp_path / "admin_promo"
    mining = tmp_path / "data-mining"
    for d in (portal, promo, mining):
        d.mkdir(exist_ok=True)

    config = {
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-key",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "test.sqlite3"),
        "PORTAL_IMAGE_DIR": str(portal),
        "ADMIN_PROMO_DIR": str(promo),
        "DATA_MINING_DIR": str(mining),
        "ADMIN_EMAIL": "administrator@pinterest.com",
        "ADMIN_PASSWORD": "admin",
    }
    config.update(overrides)
    return create_app(config)


def seed(app):
    with app.app_context():
        for name in ("Food", "Travel", "Science"):
            db.session.add(pin_category(name=name))
        db.session.add(users(name="Alice Example", email="alice@example.com",
                             password=generate_password_hash("alicepw"),
                             interests="Food,Travel"))
        db.session.add(users(name="Legacy User", email="legacy@example.com",
                             password="plaintextpw",  # pre-hashing account
                             interests="Science"))
        db.session.commit()
        alice = users.query.filter_by(email="alice@example.com").first()
        db.session.add(images(title="Sunset Beach", fields="Travel",
                              description="A beach at sunset",
                              links="https://example.com",
                              user_id=alice.id))
        db.session.add(images(title="Pasta Carbonara", fields="Food",
                              description="Roman classic",
                              links="https://example.com",
                              user_id=alice.id))
        db.session.commit()


@pytest.fixture
def app(tmp_path):
    application = make_app(tmp_path)
    seed(application)
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def csrf_app(tmp_path):
    """App with CSRF protection left ON, for testing the protection itself."""
    application = make_app(tmp_path, WTF_CSRF_ENABLED=True)
    seed(application)
    return application


def login(client, email, pwd):
    return client.post("/login", data={"email": email, "pwd": pwd})
