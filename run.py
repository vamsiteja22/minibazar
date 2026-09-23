"""Flask entry-point used by Vercel (detected via pyproject.toml + vercel.json).

For local development:  python run.py
For production servers: gunicorn run:app  (or wsgi:app)
"""
import os
import sys
import traceback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# 'app' MUST be assigned at the top level so Vercel's static scanner detects it.
app = None  # overwritten below

try:
    from app import create_app as _create_app

    app = _create_app()
    app.config["PROPAGATE_EXCEPTIONS"] = False

except Exception:  # noqa: BLE001
    from flask import Flask, Response

    app = Flask(__name__)
    _tb = traceback.format_exc()

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def _startup_error(path=""):
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Mini Bazaar – Startup Error</title>
    <style>
        body {{ font-family: system-ui, sans-serif; background:#0f172a; color:#f87171; padding:2rem; }}
        .card {{ background:#1e293b; border-radius:8px; padding:1.5rem; max-width:900px; margin:0 auto; }}
        h1 {{ color:#ef4444; margin-top:0; }}
        p {{ color:#cbd5e1; }}
        pre {{ background:#090d16; color:#f1f5f9; padding:1rem; border-radius:6px; overflow-x:auto; font-size:13px; line-height:1.5; }}
    </style>
</head>
<body>
  <div class="card">
    <h1>Mini Bazaar: Startup Error</h1>
    <p>The application failed to initialise on Vercel. Traceback:</p>
    <pre>{_tb}</pre>
  </div>
</body>
</html>"""
        return Response(html, status=500, mimetype="text/html")

if __name__ == "__main__":
    if app and not app.debug and not app.testing:
        raise SystemExit(
            "Refusing to start the development server with APP_ENV=production.\n"
            "Run the site with a production server instead, e.g.:  gunicorn run:app"
        )
    if app:
        app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")))
