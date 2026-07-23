"""Application factory for the Pinterest clone."""
import os
from datetime import datetime

import sqlalchemy as sa
from flask import Flask

from .extensions import csrf, db

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def create_app(test_config=None):
    app = Flask(__name__,
                template_folder=os.path.join(BASE_DIR, "templates"),
                static_folder=os.path.join(BASE_DIR, "static"))

    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        # Absolute path so the bundled DB keeps working with
        # Flask-SQLAlchemy 3.x, which resolves relative sqlite paths
        # against the instance/ folder
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "DATABASE_URL",
            "sqlite:///" + os.path.join(BASE_DIR, "user-data.sqlite3")),
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,  # 8 MB upload limit
        # Admin credentials — override in production via environment variables
        ADMIN_EMAIL=os.environ.get("ADMIN_EMAIL",
                                   "administrator@pinterest.com"),
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", "admin"),
        PORTAL_IMAGE_DIR=os.path.join(BASE_DIR, "static", "portal_images"),
        ADMIN_PROMO_DIR=os.path.join(BASE_DIR, "static", "admin_promo"),
        DATA_MINING_DIR=os.path.join(BASE_DIR, "data-mining"),
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    csrf.init_app(app)

    from . import admin, auth, main
    app.register_blueprint(main.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)

    @app.context_processor
    def inject_year():
        """Footer copyright year for base.html."""
        return {"year": datetime.now().year}

    with app.app_context():
        db.create_all()
        _migrate_schema()

    return app


def _migrate_schema():
    """Tiny in-place migration: add columns introduced after the original
    schema shipped. create_all() only creates missing tables, not columns."""
    inspector = sa.inspect(db.engine)
    image_cols = {col["name"] for col in inspector.get_columns("images")}
    if "filename" not in image_cols:
        db.session.execute(
            sa.text("ALTER TABLE images ADD COLUMN filename VARCHAR(200)"))
        db.session.commit()
