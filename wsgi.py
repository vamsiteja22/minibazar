import os
import sys
import traceback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    from app import create_app

    app = create_app()
    # Safety net for serverless: prevent unhandled crashes that result in FUNCTION_INVOCATION_FAILED
    app.config["PROPAGATE_EXCEPTIONS"] = False
except Exception:
    from flask import Flask, Response

    app = Flask(__name__)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def initialization_error(path=""):
        err = traceback.format_exc()
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Mini Bazaar - Startup Error</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f87171; padding: 2rem; }}
        .card {{ background: #1e293b; border-radius: 8px; padding: 1.5rem; max-width: 900px; margin: 0 auto; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
        h1 {{ color: #ef4444; font-size: 1.5rem; margin-top: 0; }}
        p {{ color: #cbd5e1; }}
        pre {{ background: #090d16; color: #f1f5f9; padding: 1rem; border-radius: 6px; overflow-x: auto; font-size: 13px; line-height: 1.5; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>Mini Bazaar: Serverless Startup Error</h1>
        <p>The application encountered an error while initializing on Vercel:</p>
        <pre>{err}</pre>
    </div>
</body>
</html>"""
        return Response(html, status=500, mimetype="text/html")

