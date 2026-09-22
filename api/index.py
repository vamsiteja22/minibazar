import os
import sys
import traceback

# Ensure application root directory is in sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    from wsgi import app
except Exception as e:
    from flask import Flask, Response

    app = Flask(__name__)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def catch_all(path):
        err = traceback.format_exc()
        return Response(
            f"<h3>Vercel Serverless Initialization Error</h3><pre>{err}</pre>",
            status=500,
            mimetype="text/html",
        )
