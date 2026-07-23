"""Database models.

Table and column names are kept identical to the original schema so the
bundled user-data.sqlite3 keeps working. Foreign keys and relationships are
declared at the ORM level; SQLite does not enforce them on the legacy tables,
but they give us joins and backrefs instead of manual query plumbing.
"""
import os

from flask import current_app, url_for

from .extensions import db


class users(db.Model):
    id = db.Column('user_id', db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100))
    password = db.Column(db.String(255))  # salted hash, never plaintext
    interests = db.Column(db.String(200))

    pins = db.relationship('images', backref='author', lazy=True)
    slug = db.relationship('user_slugs', backref='user', uselist=False,
                           lazy=True)
    saved = db.relationship('saved_pins', backref='user', lazy=True)

    @property
    def avatar_url(self):
        """Profile picture, falling back to the bundled default image."""
        name = f"user{self.id}.jpg"
        path = os.path.join(current_app.config["PORTAL_IMAGE_DIR"], name)
        if os.path.exists(path):
            return url_for('static', filename=f'portal_images/{name}')
        return url_for('static', filename='img/default-profiel.jpg')

    @property
    def follower_count(self):
        return follow_user.query.filter_by(user_email=self.email).count()

    @property
    def following_count(self):
        return follow_user.query.filter_by(follower_email=self.email).count()


class images(db.Model):
    id = db.Column('image_id', db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    fields = db.Column(db.String(300))
    description = db.Column(db.String(1000))
    links = db.Column(db.String(200))
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'))
    # Stored upload filename; legacy rows fall back to the "<id>.jpg" naming
    # convention the original app used
    filename = db.Column(db.String(200))

    @property
    def image_url(self):
        name = self.filename or f"{self.id}.jpg"
        return url_for('static', filename=f'portal_images/{name}')


class user_slugs(db.Model):
    id = db.Column('slug_id', db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'))
    bio = db.Column(db.String(1000))
    website = db.Column(db.String(100))


class pin_category(db.Model):
    id = db.Column('category_id', db.Integer, primary_key=True)
    name = db.Column(db.String(200))


class track_visits(db.Model):
    id = db.Column('visit_id', db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'))
    img_id = db.Column(db.Integer, db.ForeignKey('images.image_id'))


class admin_post(db.Model):
    id = db.Column('admin_id', db.Integer, primary_key=True)
    advertisement_title = db.Column(db.String(100))
    thought_title = db.Column(db.String(100))
    advertisement_link = db.Column(db.String(100))
    thought_link = db.Column(db.String(100))
    date = db.Column(db.String(100))

    @property
    def advert_image_url(self):
        return url_for('static', filename=f'admin_promo/adv{self.id}.jpg')

    @property
    def thought_image_url(self):
        return url_for('static', filename=f'admin_promo/thought{self.id}.jpg')


class follow_user(db.Model):
    # Follows are keyed by email (legacy schema); helper properties on users
    # hide this detail from the rest of the code
    id = db.Column('follow_id', db.Integer, primary_key=True)
    user_email = db.Column(db.String(100))
    follower_email = db.Column(db.String(100))


class saved_pins(db.Model):
    id = db.Column('save_id', db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'))
    img_id = db.Column(db.Integer, db.ForeignKey('images.image_id'))

    image = db.relationship('images', lazy=True)
