"""Quick health check of a RUNNING Mini Bazaar site (your own computer or the live website).

    python scripts/smoke_test.py http://127.0.0.1:5000
    python scripts/smoke_test.py https://your-site.onrender.com

It only reads public pages and never logs in or changes data, so it is safe to run on a
live site. Exit code 0 means every check passed. Uses only the Python standard library.
"""
import json
import sys
import urllib.error
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # we want to SEE redirects, not follow them


OPENER = urllib.request.build_opener(NoRedirect)


def fetch(base, path, method="GET", data=None):
    """Return (status, headers, body_text). HTTP errors are results, not exceptions."""
    request = urllib.request.Request(base + path, method=method, data=data)
    try:
        with OPENER.open(request, timeout=30) as response:
            return response.status, response.headers, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read().decode("utf-8", "replace")


def main(base):
    base = base.rstrip("/")
    secure_site = base.startswith("https://")
    results = []

    def check(name, passed, detail=""):
        results.append(passed)
        print(f"  {'PASS' if passed else 'FAIL'}  {name}" + (f"   ({detail})" if detail and not passed else ""))

    print(f"Smoke test for {base}\n")

    print("Site is up")
    status, headers, body = fetch(base, "/healthz")
    check("health check answers 200 with status ok", status == 200 and json.loads(body or "{}").get("status") == "ok",
          f"got {status}")
    for path, text in (("/", "Mini Bazaar"), ("/shops", "shops"), ("/products", "products"),
                       ("/login", "Login"), ("/register", "Create your account")):
        status, headers, body = fetch(base, path)
        check(f"GET {path} works", status == 200 and text.lower() in body.lower(), f"got {status}")
    status, headers, body = fetch(base, "/static/css/style.css")
    check("stylesheet is served", status == 200 and "text/css" in headers.get("Content-Type", ""), f"got {status}")
    status, headers, body = fetch(base, "/static/js/main.js")
    check("script is served", status == 200, f"got {status}")

    print("\nPages that must be protected")
    for path in ("/cart", "/orders", "/dashboard/customer", "/dashboard/admin", "/admin/users",
                 "/shopkeeper/products", "/delivery/history"):
        status, headers, _ = fetch(base, path)
        check(f"{path} sends visitors to the login page", status == 302 and "/login" in headers.get("Location", ""),
              f"got {status}")
    status, _, body = fetch(base, "/login", method="POST", data=b"email=a@b.com&password=x")
    check("a form without a security token is refused (400)", status == 400, f"got {status}")

    print("\nFriendly errors")
    status, _, body = fetch(base, "/this-page-does-not-exist")
    check("unknown page gives a friendly 404", status == 404 and "Page not found" in body, f"got {status}")
    check("no technical details are shown", "Traceback" not in body and "Werkzeug" not in body)
    status, _, _ = fetch(base, "/console")
    check("the developer console is not exposed", status == 404, f"got {status}")

    print("\nSecurity headers")
    _, headers, _ = fetch(base, "/")
    for name, needle in (("Content-Security-Policy", "script-src 'self'"), ("X-Content-Type-Options", "nosniff"),
                         ("X-Frame-Options", "DENY"), ("Referrer-Policy", "strict-origin")):
        check(f"{name} is set", needle in headers.get(name, ""))
    if secure_site:
        check("HTTPS is enforced for a year (HSTS)", "max-age=" in headers.get("Strict-Transport-Security", ""))
        _, login_headers, _ = fetch(base, "/login")
        cookie = login_headers.get("Set-Cookie", "")
        check("session cookie is Secure and HttpOnly", "Secure" in cookie and "HttpOnly" in cookie, cookie[:80])
    else:
        print("  ----  (HTTPS-only checks skipped: this address is not https)")

    passed = sum(results)
    print(f"\n{passed} of {len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    sys.exit(main(sys.argv[1]))
