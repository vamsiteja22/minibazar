"""Entry point for production servers.

    gunicorn wsgi:app              (Linux hosts such as Render)
    waitress-serve wsgi:app        (Windows)

PythonAnywhere's web tab also imports `app` from this file. The settings come from the
environment variables (APP_ENV, SECRET_KEY, DATABASE_URL, ...), see .env.example.
"""
from app import create_app

app = create_app()
