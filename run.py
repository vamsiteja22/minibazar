"""Start the app on your own computer:  python run.py

This uses Flask's built-in development server, which is NOT meant for a live website.
For a live site use wsgi.py with a production server (see docs/DEPLOYMENT.md).
"""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    if not app.debug and not app.testing:
        raise SystemExit(
            "Refusing to start the development server with APP_ENV=production.\n"
            "Run the site with a production server instead, e.g.:  gunicorn wsgi:app"
        )
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")))
