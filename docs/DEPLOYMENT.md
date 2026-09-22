# Mini Bazaar - Deployment Guide

> **Nothing has been deployed.** This guide explains how *you* deploy when you are ready. Every step below was
> prepared and verified locally with `python scripts/local_production_check.py` (production mode, real production
> server, fresh database, 23 automatic checks passing).

## 1. What was prepared

| File | Purpose |
|---|---|
| `config.py` | `development` and `production` settings, chosen by the `APP_ENV` variable |
| `wsgi.py` | Entry point used by production servers (`wsgi:app`) |
| `run.py` | Development server only. It refuses to run when `APP_ENV=production` |
| `requirements.txt` | Libraries the app needs |
| `requirements-prod.txt` | The above plus `gunicorn` (Linux) and `waitress` (Windows) |
| `Procfile` | Start command for platforms that use one (`gunicorn wsgi:app`) |
| `.env.example` | List of settings (names only, no secrets) |
| `/healthz` | URL that answers `{"status": "ok"}` when the app and database work |
| `scripts/smoke_test.py` | Tests a running site (local or live) |
| `scripts/local_production_check.py` | Runs the whole production set-up on your computer |

## 2. Environment variables

Environment variables are settings kept **outside the code**, so secrets never enter Git.

| Variable | Required | Meaning | Example |
|---|---|---|---|
| `APP_ENV` | yes (live site) | `production` turns debug off and enables strict security | `production` |
| `SECRET_KEY` | **yes in production** | Signs login cookies. 32+ random characters. The app refuses to start without it | see below |
| `DATABASE_URL` | recommended | Where data is stored. Leave out to use a local SQLite file | `postgresql://user:pass@host:5432/db` |
| `TRUSTED_PROXIES` | optional | Proxies in front of the app (default 1 in production) | `1` |
| `UPLOAD_FOLDER` | optional | Folder for uploaded product photos | `/var/data/uploads` |
| `DISPLAY_TZ_OFFSET_MINUTES` | optional | Minutes added to UTC when showing times (330 = India) | `330` |

Create a secret key (run once, keep the result private):

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

On your own computer, copy `.env.example` to `.env` and edit it. **Never commit `.env`** (it is already in `.gitignore`).

## 3. Preparing the application

### 3.1 Pre-deployment checklist

| Done | Check |
|---|---|
| ☐ | `python -m unittest discover -s tests -t .` shows `OK` |
| ☐ | `python scripts/local_production_check.py` shows `23 of 23 checks passed` |
| ☐ | `.env` is **not** in Git (`git status` must not list it) |
| ☐ | You have generated a new random `SECRET_KEY` for the live site |
| ☐ | The code is committed and pushed to GitHub (see 3.2) |
| ☐ | You know which database you will use (see 4) |

### 3.2 Put the code in Git (needed by both hosts below)

The project folder is a Git repository with no commits yet. From the project folder:

```bash
git add .
git status            # check: .env, venv/ and *.db must NOT be listed
git commit -m "Mini Bazaar - complete project"
```

Create an empty repository on GitHub, then:

```bash
git remote add origin https://github.com/<your-name>/minibazar.git
git branch -M main
git push -u origin main
```

## 4. Database

| Choice | Good for | Notes |
|---|---|---|
| **SQLite** (a single file) | Demonstrations, small sites, PythonAnywhere | Simple. Needs a disk that is **kept** between restarts |
| **PostgreSQL** | Larger sites, hosts with temporary disks (Render) | Set `DATABASE_URL`; install `psycopg2-binary` |

Database commands (run with the same environment variables as the live site):

```bash
flask --app wsgi init-db          # creates the tables and default categories (safe to repeat)
flask --app wsgi create-admin     # creates the first admin (asks for a password)
flask --app wsgi upgrade-db       # adds new columns after an update (also runs automatically at start)
```

Approve shops with the admin pages (Admin > Shops) once you have logged in as the admin.

> The automated tests run on SQLite. The code uses portable queries so PostgreSQL works, but test your live site with
> the smoke test and a manual walk-through.

**Backups:** SQLite - copy the `.db` file regularly. PostgreSQL - use the host's backup feature or `pg_dump`.

## 5. Running in production

The development server (`python run.py`) is **not** for real visitors. Use a production server:

| Where | Command |
|---|---|
| Linux hosts (Render, VPS) | `gunicorn wsgi:app --workers 2 --timeout 60` |
| Windows | `waitress-serve --port=8000 wsgi:app` |
| PythonAnywhere | Configured in the *Web* tab (see 6) |

Production mode logs to the console. The host's dashboard shows those logs.

## 6. Option A (recommended for beginners): PythonAnywhere

Why: free account, permanent disk (so **SQLite and uploaded photos survive**), HTTPS included, no credit card.
Free accounts get a URL like `https://<username>.pythonanywhere.com`. (Check their current free-plan limits.)

1. Create an account at pythonanywhere.com.
2. Open a **Bash console** and get the code:
   ```bash
   git clone https://github.com/<your-name>/minibazar.git
   cd minibazar
   mkdir -p instance
   ```
3. Create a virtual environment and install (use the newest Python 3 offered, 3.10 or later):
   ```bash
   mkvirtualenv minibazar --python=python3.10
   pip install -r requirements-prod.txt
   ```
4. Create the database and admin, using the live settings:
   ```bash
   export APP_ENV=production
   export SECRET_KEY="<paste your generated key>"
   export DATABASE_URL="sqlite:////home/<username>/minibazar/instance/minibazar.db"
   flask --app wsgi init-db
   flask --app wsgi create-admin
   ```
5. **Web** tab > *Add a new web app* > *Manual configuration* > choose the same Python version.
6. On the Web tab set:
   * **Source code / Working directory:** `/home/<username>/minibazar`
   * **Virtualenv:** `/home/<username>/.virtualenvs/minibazar`
   * **Static files:** URL `/static/` → Directory `/home/<username>/minibazar/app/static`
7. Click the **WSGI configuration file** link, delete its contents and paste:
   ```python
   import os, sys

   project = "/home/<username>/minibazar"
   sys.path.insert(0, project)

   os.environ["APP_ENV"] = "production"
   os.environ["SECRET_KEY"] = "<paste your generated key>"
   os.environ["DATABASE_URL"] = "sqlite:////home/<username>/minibazar/instance/minibazar.db"

   from wsgi import app as application
   ```
   (This file is private to your account. Do not copy it into Git.)
8. Press **Reload**. Open your site. Run the smoke test from your own computer:
   ```bash
   python scripts/smoke_test.py https://<username>.pythonanywhere.com
   ```

**Updating later:** in the Bash console `cd minibazar && git pull && pip install -r requirements-prod.txt`, then
`flask --app wsgi upgrade-db` (with the same `export`s) and press **Reload**.

## 7. Option B: Render (web service + PostgreSQL)

Why: a modern platform with automatic deploys from GitHub. **Limits to know:** the free web service's disk is
temporary (product photos disappear on redeploy unless you add a paid persistent disk), it "sleeps" when idle, and
free databases may expire - check Render's current free-tier terms before the demo.

1. Push the code to GitHub (3.2).
2. In `requirements-prod.txt` remove the `#` in front of `psycopg2-binary`, commit and push.
3. Render dashboard > **New +** > **PostgreSQL**. Copy its **Internal Database URL**.
4. **New +** > **Web Service** > connect your GitHub repository, then:
   * **Runtime:** Python 3
   * **Build command:** `pip install -r requirements-prod.txt`
   * **Start command:** `flask --app wsgi init-db && gunicorn wsgi:app --workers 2 --timeout 60`
     (`init-db` is safe to repeat; it makes sure the tables exist)
   * **Environment variables:** `APP_ENV=production`, `SECRET_KEY=<generated>`, `DATABASE_URL=<Internal Database URL>`, `PYTHON_VERSION=3.12.3`
   * **Health check path:** `/healthz`
5. Deploy. Create the first admin **from your own computer** using the database's *External* URL:
   ```bash
   # Windows PowerShell
   $env:APP_ENV="production"; $env:SECRET_KEY="<generated>"; $env:DATABASE_URL="<External Database URL>"
   flask --app wsgi create-admin
   ```
6. Run `python scripts/smoke_test.py https://<your-service>.onrender.com`.

## 8. Testing the live application

1. **Smoke test** (safe, read-only): `python scripts/smoke_test.py <your-url>`. On an `https://` address it also checks
   HSTS and that the session cookie is `Secure` and `HttpOnly`.
2. **Manual walk-through** (about 10 minutes), using `docs/TEST_PLAN.md` cases as a guide:
   * Register a customer, a shopkeeper and a delivery partner. Log in as the admin.
   * Admin approves the shop; the shopkeeper adds a product with a photo.
   * The customer searches, adds to cart, checks out.
   * The shopkeeper accepts, prepares and marks the order ready; the admin assigns the partner; the partner delivers.
   * The customer leaves a review; the shopkeeper opens Analytics.
3. Check the host's **logs** for errors.

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| App will not start: "SECRET_KEY is missing or too weak" | Variable not set or shorter than 32 characters | Set a generated `SECRET_KEY` |
| "Refusing to start the development server" | You ran `python run.py` with `APP_ENV=production` | Use `gunicorn wsgi:app` / the host's server |
| Pages have no styling (PythonAnywhere) | Static files mapping missing | Add `/static/` → `.../app/static` on the Web tab |
| Login keeps returning to the login page | Site opened over `http://` while cookies are `Secure` | Use the `https://` address |
| "That page expired" on every form | `SECRET_KEY` changed, or cookies blocked | Keep the key constant; enable cookies |
| `no such table` | Database not created | Run `flask --app wsgi init-db` with the live `DATABASE_URL` |
| `no such column` after an update | Old database | Run `flask --app wsgi upgrade-db` (or restart the app) |
| Uploaded photos vanish (Render) | Temporary disk | Use a persistent disk or accept the emoji placeholders for the demo |
| `database is locked` (SQLite) | Many writers at once | Fine for a demo; move to PostgreSQL for real traffic |

## 10. Security reminders for the live site

* Use a new `SECRET_KEY`, never the development one; keep it out of Git and screenshots.
* Always browse the live site over `https://`.
* Create the admin with the terminal command, not in the database by hand.
* Do not run `seed-demo-orders` on a live site (it is disabled in production anyway).
* Full details: `docs/SECURITY_REVIEW.md`.
