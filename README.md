# Pinterest-Flask

A Pinterest clone built with Flask — pins, profiles, follows and saves, with a
collaborative-filtering recommendation engine at its core.

## Features

- **Personalised home feed** — logged-in users see pins recommended by
  user-user collaborative filtering (TruncatedSVD over interests, uploads and
  visit history); everyone else gets the full catalogue
- **Lazy-loaded feed** — the grid serves 24 pins at a time and streams more as
  you scroll (IntersectionObserver + paginated fragment API), with native
  `loading="lazy"` images throughout
- **Full-text search** across pin titles, categories and descriptions
- **Pins** — upload, categorise, save, download and share images
- **Profiles & follows** — bios, websites, profile pictures, follower counts
- **Admin portal** — daily advertisement and thought-of-the-day posts
- **Security** — hashed passwords (Werkzeug/scrypt), CSRF-protected forms,
  validated image uploads, environment-driven secrets
- Responsive Bootstrap 5 UI, no jQuery

## Getting Started

Requires Python 3.10+.

```bash
python -m venv .venv
.venv/Scripts/activate      # Windows (use `source .venv/bin/activate` on Linux/Mac)
pip install -r requirements.txt
python app.py
```

The app runs at http://localhost:8000. The bundled `user-data.sqlite3` ships
with seed categories and images; tables (and newer columns) are created and
migrated automatically on first run.

For production, the Procfile runs `gunicorn wsgi:app`.

### Configuration

All configuration is via environment variables:

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Flask session signing key | dev-only value — set in production |
| `DATABASE_URL` | SQLAlchemy database URI | bundled SQLite file |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Admin login | `administrator@pinterest.com` / `admin` |
| `FLASK_DEBUG` | Set to `0` to disable debug mode | `1` |

Passwords are stored as salted hashes. Accounts created by older versions of
the app are upgraded to hashed passwords automatically on their next login.

## Project Layout

```
app.py               # dev entry point (create_app)
wsgi.py              # production entry point (gunicorn wsgi:app)
pinterest/           # application package
  __init__.py        #   app factory, config, schema migration
  extensions.py      #   db + CSRF extension instances
  models.py          #   ORM models with relationships
  auth.py            #   login / register / logout blueprint
  main.py            #   feed, search, pins, profiles, follows
  admin.py           #   admin promo posts
  recommender.py     #   collaborative filtering (background recompute)
templates/           # Jinja templates (Bootstrap 5)
static/              # stylesheet, JS, uploaded images
data-mining/         # pickled similarity model
tests/               # pytest suite
```

### Running the tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite covers routes, auth guards, password hashing and migration, pin
posting with upload validation, saves/follows, search, feed pagination and
CSRF enforcement.

## How the Recommendations Work

Each user's interests, uploads and pin visits are folded into a user × category
crosstab matrix, reduced with TruncatedSVD, and turned into a user-user
correlation matrix. The home feed surfaces pins viewed by the most similar
users. The model is recomputed in a background thread whenever new content is
posted, and new users fall back to the generic feed until they appear in the
matrix.

## Motivation

This project was made as a part of creating something unique with my Flask
skills after becoming proficient in developing applications with Django. I am
not that fluent with frontend development but knew bits and pieces of
Bootstrap, so I wanted to create a masterpiece of my work — and what could be
more appealing than a Pinterest clone? Since Pinterest is all about organizing
and rendering images, this was a must-try.

## Roadmap

- Boards (the one major Pinterest feature not implemented)
- Visual similarity (e.g. image embeddings) for the "More like this" section
- Move uploads to object storage instead of the local `static/` folder
- Follow/save actions without full page reloads

## Attributions

- Pinterest, for the logo used on the site — this is a small educational
  clone, so things were kept as close to the original as possible
- [wowthemesnet/template-pintereso-bootstrap-html](https://github.com/wowthemesnet/template-pintereso-bootstrap-html)
  provided the rough idea for the original index template, though the entirety
  of it has since been rewritten
