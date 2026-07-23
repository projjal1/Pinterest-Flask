"""Route, auth and feature tests for the Pinterest clone."""
import io
import os
import re

from PIL import Image as PILImage

from conftest import login
from pinterest.extensions import db
from pinterest.main import PAGE_SIZE
from pinterest.models import follow_user, images, saved_pins, users


def pin_ids(payload):
    """Pin ids linked from rendered feed card markup."""
    return set(re.findall(rb'href="/view/(\d+)"', payload))


def png_bytes():
    buf = io.BytesIO()
    PILImage.new("RGB", (16, 16), "red").save(buf, "PNG")
    buf.seek(0)
    return buf


# ------------------------------------------------------------ public pages
def test_home_anonymous(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"Sunset Beach" in r.data


def test_category_filter(client):
    r = client.get("/Food")
    assert r.status_code == 200
    assert b"Pasta Carbonara" in r.data
    assert b"Sunset Beach" not in r.data


def test_login_and_register_pages(client):
    assert client.get("/login").status_code == 200
    r = client.get("/register")
    assert r.status_code == 200
    assert b"Food" in r.data  # categories rendered as interests


def test_today_page(client):
    assert client.get("/today").status_code == 200


def test_view_photo(app, client):
    with app.app_context():
        img = images.query.first()
    r = client.get(f"/view/{img.id}")
    assert r.status_code == 200
    assert b"More like this" in r.data


def test_view_missing_photo_404(client):
    assert client.get("/view/999999").status_code == 404


def test_search(client):
    r = client.get("/search?q=pasta")
    assert r.status_code == 200
    assert b"Pasta Carbonara" in r.data
    assert b"Sunset Beach" not in r.data

    r = client.get("/search?q=")
    assert r.status_code == 200


# ------------------------------------------------------------- auth guards
def test_admin_post_requires_admin(client):
    assert client.get("/admin_post").status_code == 403


def test_author_and_post_require_login(client):
    for path in ("/author", "/post"):
        r = client.get(path)
        assert r.status_code == 200
        assert b"log in" in r.data


def test_logout_when_not_logged_in(client):
    assert client.get("/logout").status_code == 302


def test_admin_login(client):
    r = login(client, "administrator@pinterest.com", "admin")
    assert r.status_code == 302
    assert client.get("/admin_post").status_code == 200


def test_wrong_password(client):
    r = login(client, "alice@example.com", "wrong")
    assert r.status_code == 200
    assert b"Wrong email" in r.data


# ---------------------------------------------------------------- accounts
def test_register_hashes_password_and_rejects_duplicates(app, client):
    r = client.post("/register", data={
        "fname": "Bob", "lname": "Builder", "email": "bob@example.com",
        "pwd": "bobpw", "int": ["Food", "Science"]})
    assert r.status_code == 302

    with app.app_context():
        bob = users.query.filter_by(email="bob@example.com").first()
        assert bob is not None
        assert bob.password.startswith(("pbkdf2:", "scrypt:"))
        assert bob.interests == "Food,Science"

    r = client.post("/register", data={
        "fname": "Bob2", "lname": "B", "email": "bob@example.com", "pwd": "x"})
    assert b"already exists" in r.data


def test_legacy_plaintext_password_is_migrated(app, client):
    r = login(client, "legacy@example.com", "plaintextpw")
    assert r.status_code == 302

    with app.app_context():
        legacy = users.query.filter_by(email="legacy@example.com").first()
        assert legacy.password.startswith(("pbkdf2:", "scrypt:"))

    client.get("/logout")
    assert login(client, "legacy@example.com", "plaintextpw").status_code == 302


# ---------------------------------------------------------------- features
def test_post_pin_stores_filename_and_file(app, client):
    login(client, "alice@example.com", "alicepw")
    r = client.post("/post", data={
        "iname": "Test Pin", "desc": "desc", "cat": "Food",
        "links": "example.com/pin",
        "img": (png_bytes(), "upload.png")},
        content_type="multipart/form-data")
    assert r.status_code == 200
    assert b"Image Saved" in r.data

    with app.app_context():
        pin = images.query.filter_by(title="Test Pin").first()
        assert pin is not None
        assert pin.filename == f"{pin.id}.jpg"
        assert pin.links == "https://example.com/pin"  # scheme added
        assert os.path.exists(os.path.join(
            app.config["PORTAL_IMAGE_DIR"], pin.filename))


def test_post_pin_rejects_non_image(client):
    login(client, "alice@example.com", "alicepw")
    r = client.post("/post", data={
        "iname": "Bad Pin", "desc": "d", "cat": "Food", "links": "",
        "img": (io.BytesIO(b"not an image"), "evil.exe")},
        content_type="multipart/form-data")
    assert b"valid image" in r.data


def test_save_pin_once(app, client):
    login(client, "alice@example.com", "alicepw")
    with app.app_context():
        img = images.query.first()

    assert client.get(f"/save_pins/{img.id}").status_code == 302
    assert client.get(f"/save_pins/{img.id}").status_code == 302  # duplicate

    with app.app_context():
        assert saved_pins.query.filter_by(img_id=img.id).count() == 1


def test_follow_and_no_self_follow(app, client):
    login(client, "legacy@example.com", "plaintextpw")

    r = client.post("/follow/alice@example.com")
    assert r.status_code == 302
    r = client.post("/follow/legacy@example.com")  # self-follow ignored
    assert r.status_code == 302

    with app.app_context():
        rows = follow_user.query.all()
        assert len(rows) == 1
        assert rows[0].user_email == "alice@example.com"
        assert rows[0].follower_email == "legacy@example.com"


def test_profile_update_and_own_profile_view(app, client):
    login(client, "alice@example.com", "alicepw")

    r = client.post("/author", data={"bio": "I take photos",
                                     "url": "alice.example.com"})
    assert r.status_code == 302

    with app.app_context():
        alice = users.query.filter_by(email="alice@example.com").first()
        assert alice.slug is not None
        assert alice.slug.bio == "I take photos"
        assert alice.slug.website == "https://alice.example.com"

    r = client.get("/profile")
    assert r.status_code == 200
    assert b"I take photos" in r.data


# ------------------------------------------------------ lazy-loaded feed
def seed_many_pins(app, count):
    with app.app_context():
        alice = users.query.filter_by(email="alice@example.com").first()
        for i in range(count):
            db.session.add(images(title=f"Extra Pin {i}", fields="Science",
                                  description="filler", links="",
                                  user_id=alice.id))
        db.session.commit()
        return images.query.count()


def test_home_serves_one_page_with_sentinel(app, client):
    total = seed_many_pins(app, PAGE_SIZE + 6)

    r = client.get("/?seed=42")
    assert r.status_code == 200
    assert len(pin_ids(r.data)) == PAGE_SIZE
    assert b'id="feed-sentinel"' in r.data
    assert b'data-has-more="1"' in r.data
    assert total > PAGE_SIZE


def test_api_pins_pagination_is_stable_and_disjoint(app, client):
    total = seed_many_pins(app, PAGE_SIZE + 6)

    first = client.get("/?seed=42")
    second = client.get("/api/pins?page=2&seed=42&category=All")
    assert second.status_code == 200
    data = second.get_json()
    assert data["has_more"] is False  # everything fits in two pages

    page1, page2 = pin_ids(first.data), pin_ids(data["html"].encode())
    assert page1.isdisjoint(page2)  # seeded shuffle: no repeats
    assert len(page1 | page2) == total  # ...and nothing missing


def test_api_pins_search_pagination(client):
    r = client.get("/api/pins?page=1&q=pasta")
    data = r.get_json()
    assert "Pasta Carbonara" in data["html"]
    assert data["has_more"] is False


def test_feed_images_are_lazy(client):
    r = client.get("/")
    assert b'loading="lazy"' in r.data


# -------------------------------------------------------------------- CSRF
def test_csrf_blocks_forms_without_token(csrf_app):
    client = csrf_app.test_client()
    r = client.post("/login", data={"email": "alice@example.com",
                                    "pwd": "alicepw"})
    assert r.status_code == 400  # missing CSRF token


def test_csrf_token_rendered_in_forms(csrf_app):
    client = csrf_app.test_client()
    r = client.get("/login")
    assert b'name="csrf_token"' in r.data
