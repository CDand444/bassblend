r"""Browser check: start htTamer with empty data, open every page in a real (headless) browser with a
full reload each time, and fail on any script error, a script that didn't load, or a page that doesn't
show. This catches what the offline tests can't: a syntax error in one of the page's scripts, two
scripts declaring the same name (the browser drops the second file), or a render that throws.

Needs Playwright:  pip install playwright && python -m playwright install chromium
Run:  python tests/browser_check.py            (not part of the offline tests: it needs a browser)
"""
from __future__ import annotations

import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port):
    tmp = tempfile.mkdtemp(prefix="bb_browser_")
    env = {**os.environ, "BASSBLEND_DATA": os.path.join(tmp, "data"), "BASSBLEND_CONFIG": os.path.join(tmp, "conf"),
           "PYTHONUNBUFFERED": "1"}
    log = open(os.path.join(tmp, "server.log"), "w", encoding="utf-8")
    p = subprocess.Popen([sys.executable, "-m", "subtune", "serve", "--port", str(port)], cwd=ROOT, env=env,
                         stdout=log, stderr=subprocess.STDOUT)
    for _ in range(120):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=2).read()
            return p, tmp
        except OSError:
            if p.poll() is not None:
                break
            time.sleep(0.5)
    p.kill()
    sys.exit("htTamer didn't start:\n" + open(os.path.join(tmp, "server.log"), encoding="utf-8").read()[-3000:])


def main():
    from playwright.sync_api import sync_playwright
    port = free_port()
    server, tmp = start_server(port)
    base = f"http://127.0.0.1:{port}"
    problems = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errs = []
            page.on("pageerror", lambda e: errs.append(f"script error: {e}"))
            page.on("console", lambda m: m.type == "error" and "Failed to load resource" not in m.text
                    and errs.append(f"console: {m.text[:300]}"))
            page.on("request", lambda r: r.url.endswith("/api/client-error") and errs.append(f"page reported: {r.post_data}"))

            page.goto(base + "/", wait_until="load")
            page.wait_for_function("typeof MENU !== 'undefined' && typeof S !== 'undefined' && !!S.terms", timeout=20000)
            page.evaluate("""async () => { await post('/api/terms', {accept: true, version: S.terms.version}); }""")
            keys = page.evaluate("MENU.filter(m => m.key).map(m => m.key)")
            if len(keys) < 20:
                problems.append(f"only {len(keys)} pages in the menu")
            for key in keys:
                errs.clear()
                page.goto(f"{base}/#/{key}", wait_until="load")
                page.reload(wait_until="load")                     # a real reload, not just a hash change
                page.wait_for_timeout(1500)
                st = page.evaluate("""(key) => {
                    const m = MENU.find(x => x.key === key);
                    const shown = !!(m && m.el && m.el.offsetParent !== null);
                    const failed = [...document.querySelectorAll('.toast')].some(t => /failed to load/i.test(t.innerText));
                    const terms = !document.querySelector('#terms') || document.querySelector('#terms').hidden;
                    return {shown, failed, terms, title: document.title};
                }""", key)
                if not st["shown"]:
                    problems.append(f"#{key}: the page didn't show (title: {st['title']})")
                if st["failed"]:
                    problems.append(f"#{key}: 'part of the page failed to load'")
                if not st["terms"]:
                    problems.append(f"#{key}: the terms dialog is still up after accepting")
                problems += [f"#{key}: {e}" for e in errs]
                print(f"{'ok  ' if not errs and st['shown'] and not st['failed'] else 'FAIL'}  #{key}")
            for path, needle in (("/manual", "Safety and responsibility"), ("/build", "room")):
                errs.clear()
                page.goto(base + path, wait_until="load")
                page.wait_for_timeout(800)
                if needle.lower() not in page.content().lower():
                    problems.append(f"{path}: expected text '{needle}' missing")
                problems += [f"{path}: {e}" for e in errs]
                print(f"{'ok  ' if not errs else 'FAIL'}  {path}")
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            server.kill()
    if problems:
        print("\nProblems:\n  " + "\n  ".join(problems))
        print("\nServer log (end):\n" + open(os.path.join(tmp, "server.log"), encoding="utf-8").read()[-2000:])
        sys.exit(1)
    print("\nAll pages load without script errors.")


if __name__ == "__main__":
    main()
