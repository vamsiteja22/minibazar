"""Turn the Mermaid diagrams in docs/PROJECT_REPORT.md into PNG pictures (docs/diagrams/*.png).

    python scripts/export_diagrams.py

Handy for Word/PDF reports. Needs an internet connection (it loads the Mermaid library from a
public CDN) and an installed Edge or Chrome browser. Also proves every diagram has valid syntax.
"""
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "diagrams"
NAMES = ["system_architecture", "checkout_sequence", "er_diagram", "use_case_diagram", "dfd_level_0",
         "dfd_level_1", "order_states", "delivery_states"]


def find_browser():
    candidates = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                  r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                  r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                  r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]
    candidates += [shutil.which(n) or "" for n in ("msedge", "google-chrome", "chromium")]
    return next((c for c in candidates if c and os.path.exists(c)), None)


def page_for(diagram):
    return ("<!doctype html><meta charset='utf-8'><body style='margin:0;padding:16px;background:#fff'>"
            f"<pre class='mermaid'>{html.escape(diagram)}</pre>"
            "<script src='https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js'></script>"
            "<script>mermaid.initialize({startOnLoad:true, securityLevel:'loose'});</script>")


def main():
    browser = find_browser()
    if not browser:
        raise SystemExit("No Edge/Chrome browser found.")
    text = (ROOT / "docs" / "PROJECT_REPORT.md").read_text(encoding="utf-8")
    diagrams = re.findall(r"```mermaid\n(.*?)```", text, flags=re.S)
    OUT.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp())
    common = [browser, "--headless", "--disable-gpu", "--hide-scrollbars", "--virtual-time-budget=25000"]

    for index, diagram in enumerate(diagrams):
        name = NAMES[index] if index < len(NAMES) else f"diagram_{index + 1}"
        page = work / f"{name}.html"
        page.write_text(page_for(diagram), encoding="utf-8")

        # Pass 1: find out how big the drawn diagram is (and whether it has a syntax error).
        dom = subprocess.run(common + ["--dump-dom", page.as_uri()], capture_output=True, text=True, timeout=180).stdout
        if "Syntax error" in dom or "<svg" not in dom:
            print(f"  FAIL  {name}: the diagram has a syntax error")
            continue
        box = re.search(r'viewBox="[-\d.]+ [-\d.]+ ([\d.]+) ([\d.]+)"', dom)
        width, height = (int(float(box.group(1))) + 40, int(float(box.group(2))) + 40) if box else (1400, 1000)
        width, height = min(max(width, 400), 3000), min(max(height, 300), 4000)

        # Pass 2: photograph it at exactly that size.
        target = OUT / f"{index + 1:02d}_{name}.png"
        subprocess.run(common + [f"--window-size={width},{height}", f"--screenshot={target}", page.as_uri()],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
        print(f"  {'ok  ' if target.exists() else 'MISSING'}  {target.name}  ({width}x{height})")
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
