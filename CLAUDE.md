# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Dependencies live in a venv at `.venv` (Windows paths shown; use `.venv/bin/` on Unix):

```bash
.venv\Scripts\python -m pip install -r requirements-dev.txt   # install (includes pytest)
.venv\Scripts\python app.py                                   # dev server on http://localhost:8000
.venv\Scripts\python -m pytest tests -q                       # full test suite
.venv\Scripts\python -m pytest tests/test_app.py -k test_name # single test
```

Production entry point is `gunicorn wsgi:app` (Procfile). Config is env-driven:
`SECRET_KEY`, `DATABASE_URL`, `ADMIN_EMAIL`/`ADMIN_PASSWORD`, `FLASK_DEBUG`.

## Architecture

Flask app-factory package (`pinterest/`): `create_app(test_config)` in
`__init__.py` wires config, extensions (`extensions.py` holds unbound `db` and
`csrf`), and three blueprints — `main` (feed, search, pins, profiles, follows),
`auth` (login/register/logout), `admin` (promo posts). Templates and static
files live at the repo root, not inside the package. `app.py` is a thin dev
entry point.

### Legacy schema compatibility (important)

The bundled `user-data.sqlite3` is seed data the app must keep working with:

- Model class names are lowercase (`users`, `images`, `saved_pins`...) and map
  to the original table/column names (`user_id`, `image_id`...). **Do not
  rename tables or columns.** Relationships/FKs exist only at the ORM level;
  SQLite never enforces them on these tables.
- `db.create_all()` only creates missing tables. New **columns** must be added
  in `_migrate_schema()` (`pinterest/__init__.py`) via `ALTER TABLE` —
  see the `images.filename` migration for the pattern.
- `follow_user` is keyed by **email**, not user id (legacy). The
  `users.follower_count`/`following_count` properties hide this.
- Passwords are Werkzeug hashes, but legacy rows may hold plaintext:
  `verify_password()` (`utils.py`) upgrades them in place on successful login.
  Login email matching is deliberately case-insensitive.

### Auth model

Session-based, no Flask-Login. `session["username"]`/`session["email"]` are
the source of truth. The templates key off `display_nm`: `"Author"` means
anonymous, `"Admin"` means the admin — every view passes it. Admin is a
virtual user checked against env credentials, not a DB row. Guards are the
`login_required`/`admin_required` decorators in `utils.py`.

### Feed pagination contract

`main.index` renders page 1 (24 pins, `PAGE_SIZE`) with a random **seed**;
`/api/pins` re-derives the same shuffled ordering from that seed for pages 2+
and returns `{html, has_more}` where `html` is a rendered `_pin_cards.html`
fragment. `static/js/main.js` drives the infinite scroll from the
`#feed-sentinel` data attributes. If you change feed ordering or the card
markup, keep all three (route, partial, JS) in sync — tests assert pages are
disjoint and their union covers the catalogue under a fixed seed.

### Recommendations

`recommender.py`: user interests/uploads/visits → crosstab → TruncatedSVD →
user-user correlation matrix, pickled to `data-mining/`. Recompute runs in a
lock-guarded background thread (`schedule_similarity_refresh`), synchronous
when `TESTING`. `recommended_images()` must never raise — any unreadable model
(stale pandas pickles, unknown user) falls back to `[]` and the generic feed.

### Uploads

Images are stored as JPEG in `static/portal_images/` named `<image_id>.jpg`
(admin promos: `static/admin_promo/adv<id>.jpg` / `thought<id>.jpg`; avatars:
`user<user_id>.jpg`). The `images.filename` column records the name; legacy
rows fall back to the id convention via the `image_url` model property —
build URLs through those properties, not by hand. All uploads go through
`open_image_upload()` (Pillow validation + RGB conversion). The directories
are config keys (`PORTAL_IMAGE_DIR`, `ADMIN_PROMO_DIR`, `DATA_MINING_DIR`) so
tests can redirect them to tmp paths — never hardcode the static paths in
routes.

### Tests

`tests/conftest.py` builds an isolated app per test (`make_app`) with a tmp
SQLite DB, tmp upload/model dirs, and CSRF disabled (a separate `csrf_app`
fixture keeps it on to test the protection itself). Several tests assert on
literal template strings ("More like this", `id="feed-sentinel"`,
`loading="lazy"`, alert texts like "Wrong email") — keep those strings stable
or update the tests alongside.
