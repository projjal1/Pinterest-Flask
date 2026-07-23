# Pinterest-Flask
A Pinterest Clone made using Flask in Python that deals with pins and has embedded AI at its core end.

## Motivation 
This project was made as a part of creating something unique with my Flask skills essentially after being proficient in developing applications with Django. Also, I am not that much
fluent with developing Frontend but knew bits-and-pieces of Bootstrap. So, I wanted to create a masterpiece of my work and what could be more appealing than Pinterest clone. 
Since Pinterest is all about organizing and rendering images this was a must-try.

### Code Dependancies
The code dependancies for the project are : 
<ul>
<li>Python 3.10+
<li>Flask 3
<li>Flask-SQLAlchemy 3 for the SQLite database management
<li>scikit-learn
<li>Pillow
<li>gunicorn
<li>pandas 
<li>numpy
</ul>

## Getting Started

```bash
python -m venv .venv
.venv/Scripts/activate      # Windows (use `source .venv/bin/activate` on Linux/Mac)
pip install -r requirements.txt
python app.py
```

The app runs at http://localhost:8000. The bundled `user-data.sqlite3` ships with seed
categories and images; tables (and newer columns) are created/migrated automatically
on first run.

### Project layout

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
tests/               # pytest suite
```

### Running the tests

```bash
pip install -r requirements-dev.txt
pytest
```

### Configuration (environment variables)

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Flask session signing key | dev-only value — set in production |
| `DATABASE_URL` | SQLAlchemy database URI | bundled SQLite file |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Admin login | `administrator@pinterest.com` / `admin` |
| `FLASK_DEBUG` | Set to `0` to disable debug mode | `1` |

Passwords are stored as salted hashes (Werkzeug). Accounts created by older versions
of the app are upgraded to hashed passwords automatically on their next login.

## AI feature
I have used Collaborative filtering for generating recommended images in the home screen for logged-in users.

## Features 
The project has most of the features as in original Pinterest site other than "BOARDS" section. 
<ul>
<li>Material UI (Bootstrap 5)
<li>Full-text pin search
<li>Save images(pins), follow users
<li>Admin can upload specific advertisements and thoughts
<li>Fluid experience
<li>Track user activity for generating recommendations based on similar behaviour
<li>CSRF-protected forms and hashed passwords
</ul>

## What is Left to be Done ?
The project is still under development although it may look as if complete. <br>The following features need to be added.
<ul><li>Search functionality (enhanced) <li>Usage of OpenCV to generated similar images in "MORE LIKE THIS" section
<li>Optimization for mobile devices</ul>

### Attributions 
I would like to mention the following sources whose artifacts I have used to make this project
<ul>
<li>Pinterest for using the Logo on the site (Since this is just a small try-out clone attempt, so I wanted to keep things as original as possible)
<li>https://github.com/wowthemesnet/template-pintereso-bootstrap-html repo has been very beneficial for generating the index template, although the entirety of it was modified 
but  was helpful in giving the rough idea.
</ul>
