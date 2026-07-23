"""Development entry point. Production uses wsgi.py via gunicorn."""
import os

from pinterest import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "1") == "1", port=8000)
