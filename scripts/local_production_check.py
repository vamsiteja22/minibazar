"""Run Mini Bazaar the way a live server would, then smoke-test it. Nothing is deployed.

    python scripts/local_production_check.py

It uses a throw-away database and a random secret key, starts the app in production mode
with a real production web server (waitress), runs scripts/smoke_test.py against it, and
then shuts everything down. Your own database and .env file are not touched.
"""
import os
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = "5077"


def run(args, env):
    return subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)


def main():
    folder = tempfile.mkdtemp(prefix="minibazar_prod_check_")
    env = dict(os.environ)
    env.update(
        APP_ENV="production",
        SECRET_KEY=secrets.token_hex(32),
        DATABASE_URL="sqlite:///" + os.path.join(folder, "live.db").replace("\\", "/"),
        UPLOAD_FOLDER=os.path.join(folder, "uploads"),
    )
    env.pop("FLASK_DEBUG", None)
    flask = [sys.executable, "-m", "flask", "--app", "wsgi"]

    print("1. Creating the database (flask init-db) ...")
    result = run(flask + ["init-db"], env)
    print("  ", (result.stdout or result.stderr).strip().splitlines()[-1])
    if result.returncode:
        return result.returncode

    print("2. Creating an admin account from the terminal (flask create-admin) ...")
    result = run(flask + ["create-admin", "--name", "Check Admin", "--email", "check@example.com",
                          "--password", "a-long-test-password"], env)
    print("  ", (result.stdout or result.stderr).strip().splitlines()[-1])
    if result.returncode:
        return result.returncode

    print(f"3. Starting the production server (waitress) on port {PORT} ...")
    server = subprocess.Popen([sys.executable, "-m", "waitress", f"--port={PORT}", "wsgi:app"],
                              cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/healthz", timeout=2)
                break
            except Exception:
                if server.poll() is not None:
                    print("   The server stopped:", server.stderr.read()[-800:])
                    return 1
                time.sleep(0.5)
        print("4. Running the smoke test ...\n")
        return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "smoke_test.py"),
                               f"http://127.0.0.1:{PORT}"], env=env).returncode
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        print("\nServer stopped. Temporary files were in:", folder)


if __name__ == "__main__":
    sys.exit(main())
