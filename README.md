# Mini Bazaar

**A hyperlocal e-commerce platform that connects customers with nearby local shopkeepers.**

Customers find nearby shops, search products and order with cash on delivery. Shopkeepers manage their shop, stock and
orders. Delivery partners handle deliveries. Admins approve shops and run the platform.

![Home page](docs/screenshots/01_home.png)

## Features

| Role | What they can do |
|---|---|
| **Customer** | Browse and search, find shops near them, cart (one shop per order), checkout, track and cancel orders, review delivered products |
| **Shopkeeper** | Shop profile with map location, products with photos, stock, low-stock alerts, order handling (accept, prepare, ready), sales analytics |
| **Delivery partner** | Assigned deliveries with pickup and drop-off details, accept, pick up, deliver, delivery history |
| **Admin** | Statistics, approve or reject shops, manage users and categories, view all orders, assign delivery partners |

Order journey: *Customer orders → Shopkeeper accepts, prepares, marks ready → Admin assigns a delivery partner → Partner picks up and delivers.*

## Technology

Python 3 · Flask (application factory, blueprints) · SQLAlchemy · SQLite (PostgreSQL supported) · Jinja2 · HTML, CSS, JavaScript ·
Flask-Login · Flask-WTF · gunicorn / waitress for production. Architecture: a modular monolith (routes → services → models).

## Quick start (your own computer)

```bash
python -m venv venv
venv\Scripts\activate              # Windows      (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt

copy .env.example .env             # macOS/Linux: cp .env.example .env
flask --app run init-db            # creates the tables and default categories
flask --app run create-admin       # creates your admin account
python run.py                      # open http://127.0.0.1:5000
```

Register a shopkeeper, create a shop, then approve it as the admin (Admin > Shops) so customers can see it.
For sample data while testing: `flask --app run seed-demo-orders --email <shopkeeper email>` (development only).

## Tests

```bash
python -m unittest discover -s tests -t .          # 367 automated tests
python scripts/local_production_check.py           # runs the site in production mode + smoke test
```

## Documentation

| Document | Contents |
|---|---|
| [Project report](docs/PROJECT_REPORT.md) | Abstract, problem, objectives, scope, architecture, ER / use-case / data-flow diagrams, modules, screenshots, testing, future work |
| [Test plan](docs/TEST_PLAN.md) | 131 test cases (ID, steps, expected result, actual result and status placeholders) and the automated suite |
| [Security review](docs/SECURITY_REVIEW.md) | Findings, fixes and known limitations |
| [Deployment guide](docs/DEPLOYMENT.md) | Environment variables, production server, PythonAnywhere and Render steps, live smoke test |
| [Presentation guide](docs/PRESENTATION.md) | Slide outline, demo script, viva questions |
| `docs/screenshots/`, `docs/diagrams/` | Pictures for reports and slides |

## Settings (environment variables)

| Variable | Meaning |
|---|---|
| `APP_ENV` | `development` (default) or `production` |
| `SECRET_KEY` | Required in production: 32+ random characters (`python -c "import secrets; print(secrets.token_hex(32))"`) |
| `DATABASE_URL` | Optional: SQLite file or PostgreSQL address |
| `TRUSTED_PROXIES`, `UPLOAD_FOLDER`, `DISPLAY_TZ_OFFSET_MINUTES` | Optional, see `.env.example` |

Never commit the `.env` file.

## Useful commands

```bash
flask --app run approve-shop --email <owner>    # approve a shop (--revoke to hide it)
flask --app run list-shops                       # list shops and their approval state
flask --app run upgrade-db                       # add new columns to an older database
python scripts/smoke_test.py <url>               # health check of a running site
python scripts/capture_screenshots.py            # regenerate docs/screenshots
python scripts/export_diagrams.py                # regenerate docs/diagrams
```

## Project structure

```
app/          application: models, routes, services (business rules), templates, static files
tests/        367 automated tests
scripts/      smoke test, production check, screenshot and diagram generators
docs/         report, test plan, security review, deployment guide, presentation, pictures
config.py     development / production settings          wsgi.py   production entry point
run.py        development server                          Procfile  start command for hosts
```
