"""Root Flask app entry-point for Vercel and other hosts.

Vercel scans this file for a top-level 'app' variable.
The real application factory lives in app/__init__.py.
"""
import os
import sys
import traceback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# --- Always assign 'app' at the top level so Vercel's static scanner finds it ---
app = None  # will be replaced below; needed for Vercel detection

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
    <p>The application failed to initialise. Traceback:</p>
    <pre>{_tb}</pre>
  </div>
</body>
</html>"""
        return Response(html, status=500, mimetype="text/html")

if __name__ == "__main__":
    app.run()
