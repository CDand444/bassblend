r"""Browser check of the page's buttons: click each one that doesn't touch hardware and make sure the page shows the new data
by itself, with no reload; and change the stored data behind the page's back and make sure the page catches up.

Starts htTamer with empty data (like tests/browser_check.py), so no sound, no receiver, no miniDSP.
Needs Playwright:  pip install playwright && python -m playwright install chromium
Run:  python tests/browser_actions.py            (not part of the offline tests: it needs a browser)
"""
from __future__ import annotations

import json
import math
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import browser_check as bc                                   # noqa: E402

PROBLEMS: list[str] = []


def check(name, ok, detail=""):
    print(("ok    " if ok else "FAIL  ") + name + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        PROBLEMS.append(name)


def until(page, js, timeout=4000):
    """True when the JS expression becomes truthy within the time (the page polls once a second)."""
    try:
        page.wait_for_function(js, timeout=timeout)
        return True
    except Exception:                                        # noqa: BLE001
        return False


def main():
    from playwright.sync_api import sync_playwright
    port = bc.free_port()
    server, tmp = bc.start_server(port)
    base = f"http://127.0.0.1:{port}"
    data = pathlib.Path(tmp) / "data"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1400, "height": 1100})
            errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.on("dialog", lambda d: d.accept())
            page.goto(base + "/#/room")
            page.wait_for_function("typeof MENU !== 'undefined' && typeof S !== 'undefined' && !!S.terms", timeout=20000)
            page.evaluate("async () => { await post('/api/terms', {accept: true, version: S.terms.version}); }")
            page.goto(base + "/#/room")
            page.reload()
            page.wait_for_timeout(1200)

            # ---- Room: Save shows in the stored state and the plan without a reload
            page.fill("#rL", "20"); page.fill("#rW", "13"); page.fill("#rH", "8")
            page.click("#roomSave")
            check("Room: Save updates the page's state", until(page, "S.room && S.room.room.length_m > 6"))
            check("Room: the plan is drawn after Save", page.locator("#plan svg").count() == 1)

            # ---- Screen, furniture and soffits: change the drawing at once, and survive Save
            page.select_option("#scKind", "projector"); page.fill("#scDiag", "120"); page.check("#scAt")
            check("Screen: the plan shows it as you type", until(page, "document.querySelector('#plan svg text') && document.querySelector('#plan').textContent.includes('acoustically transparent')"))
            page.click("#addCouch"); page.click("#addRiser")
            check("Furniture: couch and riser appear on the plan", page.locator("#plan svg g.fu").count() == 2)
            page.click("#roomSave")
            check("Save keeps the screen and furniture", until(page, "S.room.screen && S.room.screen.at && S.room.furniture.length == 2"))
            page.click("#planView [data-pv='3d']")
            check("3D view opens with the room", page.locator("#plan3dBox").is_visible())
            page.click("#planView [data-pv='2d']")

            # ---- Enclosure: open plan opens a whole side, and the page and the saved room agree
            page.select_option("#enLevel", "open")
            check("Enclosure: Open plan opens a whole side", until(page, "roomShape.wall_openings.some(o => o.kind === 'opening') && document.querySelectorAll('[data-enwall]:checked').length === 1"))
            page.click("#roomSave")
            check("Enclosure: it is saved with the room", until(page, "S.room.room.wall_openings.some(o => o.kind === 'opening')"))
            page.select_option("#enLevel", "closed")
            check("Enclosure: Closed removes the openings", until(page, "roomShape.wall_openings.filter(o => o.kind === 'opening').length === 0"))
            page.click("#roomSave")

            page.wait_for_timeout(1000)                                  # the save above re-fills the form: let it finish
            # ---- Where you live: an apartment with someone below shows neighbor advice and is saved with the room
            page.select_option("#dwKind", "apartment")
            page.check("#dwBelow")
            check("Dwelling: advice appears for a shared floor", until(page, "document.querySelector('#dwInfo').textContent.includes('Keep it modest')"))
            page.click("#roomSave")
            check("Dwelling: it is saved with the room", until(page, "S.room.dwelling && S.room.dwelling.kind === 'apartment' && S.room.dwelling.shared.below === true"))
            page.select_option("#dwKind", "")
            page.click("#roomSave")
            check("Dwelling: clearing it removes it", until(page, "!S.room.dwelling"))

            # ---- Risers: a couch added after a riser sits on it, the page says so, and the 3D view draws both as one object
            page.wait_for_timeout(500)
            page.click("#addRiser")
            page.click("#addCouch")
            check("Riser: a new couch sits on the riser", until(page, "[...document.querySelectorAll('#couchRows .fuinfo')].some(e => e.textContent.startsWith('Sits on'))"))
            check("Riser: the 3D scene groups the couch with its riser", page.evaluate("(() => { const m = fuMarks3d(fuRead()); return m.some(x => x.boxes.length >= 7); })()"))
            check("Treatment 3D: panels, clouds, rugs and traps become solids", page.evaluate("""(() => { const rm = {length_m: 6, width_m: 4, height_m: 2.5};
              const p = {room: {W: 4, L: 6, H: 2.5}, shape: {}, items: [
                {id: 'side', wall: 'left', kind: 'absorber', tier: 1, qty: 4, thickness_in: 2, rect: {x0: 0, x1: 0, y0: 1, y1: 3, n: [-1, 0]}, zone: {b: [0.5, 2]}},
                {id: 'cloud', wall: 'ceiling', kind: 'cloud', tier: 2, qty: 3, thickness_in: 4, rect: {x0: 1, x1: 3, y0: 2, y1: 4}},
                {id: 'rug', wall: 'floor', kind: 'rug', tier: 3, qty: 1, rect: {x0: 1, x1: 3, y0: 0, y1: 3}},
                {id: 'corner_traps', wall: 'corners', kind: 'bass trap', tier: 1, qty: 1, thickness_in: 12, corners: [{x_m: 0, y_m: 0, name: 'front left'}]}]};
              const s = v3Treatment(p, rm); return s.length === 4 && s.every(x => x.boxes.length >= 1 && x.boxes.every(b => b.pts.length >= 3 && b.z1 > b.z0)); })()"""))
            page.click("#planView [data-pv='3d']")
            check("Riser: the 3D room view draws without errors", page.locator("#plan3dBox").is_visible())
            page.click("#planView [data-pv='2d']")

            # ---- Sub aim and size: the pick sets the angle, the card says what it points at, the 3D sub turns and takes its size
            page.evaluate("(() => { const c = document.querySelector('#subRows .subcard'); if (!c.querySelector('.aimsel')) { const k = [...document.querySelectorAll('#subRows .subadd')][0]; k && k.click(); } })()")
            page.wait_for_timeout(1500)
            has_sub = page.evaluate("!!document.querySelector('#subRows .subcard .aimsel')")
            if has_sub:
                page.evaluate("(() => { const c = document.querySelector('#subRows .subcard .aimsel').closest('.subcard'); const set = (f, v) => { const i = c.querySelector(`[data-f='${f}']`); i.value = v; i.dispatchEvent(new Event('input', {bubbles: true})); }; set('x_m', '2'); set('y_m', '5'); })()")
                page.evaluate("(() => { const sel = document.querySelector('#subRows .subcard .aimsel'); sel.value = '90'; sel.dispatchEvent(new Event('change', {bubbles: true})); })()")
                check("Sub aim: the pick sets the angle", page.evaluate("document.querySelector('#subRows .subcard [data-f=aim_deg]').value === '90'"))
                check("Sub aim: the card says what it points at", until(page, "document.querySelector('#subRows .subcard .aiminfo').textContent.includes('Points at wall')"))
                check("Sub aim: the 3D sub takes the angle and a typed size", page.evaluate("""(() => { const r = readRoom(); const k = Object.keys(r.subs)[0]; r.subs[k].width_in = 20; r.subs[k].height_in = 24; r.subs[k].depth_in = 22;
                  const m = v3Subs(r)[0].boxes[0]; const xs = m.pts.map(p => p[0]), ys = m.pts.map(p => p[1]); return Math.abs((Math.max(...xs) - Math.min(...xs)) - 0.508) < 0.001 || Math.abs((Math.max(...ys) - Math.min(...ys)) - 0.508) < 0.001; })()"""))
            page.wait_for_timeout(300)

            check("Treatment 3D: no panel tile over a door", page.evaluate("""(() => { const rm = {length_m: 6, width_m: 4, height_m: 2.5};
              const p = {room: {W: 4, L: 6, H: 2.5}, shape: {openings: [{wall: 0, from_m: 1, width_m: 1, height_m: 2.03, kind: 'door'}]}, items: [
                {id: 'front', wall: 'front', kind: 'absorber', tier: 1, qty: 8, thickness_in: 4, rect: {x0: 0, x1: 4, y0: 0, y1: 0, n: [0, -1]}, zone: {edge: 0, s: [0, 4], b: [0.3, 1.5]}}]};
              const tiles = v3Treatment(p, rm)[0].boxes; if (!tiles.length) return false;
              return tiles.every(b => { const xs = b.pts.map(q => q[0]); return Math.max(...xs) <= 1.0 + 1e-6 || Math.min(...xs) >= 2.0 - 1e-6; }) && tiles.length < 8; })()"""))

            # ---- Speaker placement in 3D: recommended spots, recorded ones, lines between them; ceiling speakers hang from a soffit
            check("Placement 3D: speakers, lines and the soffit-aware ceiling", page.evaluate("""(() => {
              const rm = {length_m: 6, width_m: 4, height_m: 2.4, soffits: [{wall: 0, from_m: 0, length_m: 4, depth_m: 2, bottom_m: 2.0}]};
              if (Math.abs(RoomView.ceilAt(rm, 2, 1) - 2.0) > 1e-6 || Math.abs(RoomView.ceilAt(rm, 2, 4) - 2.4) > 1e-6) return false;
              const p = {seat: {x_m: 2, y_m: 4, z_m: 1.05}, speakers: [{id: 'FL', x_m: 0.8, y_m: 0.4, z_m: 1.05, kind: 'bed'}, {id: 'TFL', x_m: 0.8, y_m: 1.2, z_m: 2.0, kind: 'height'}],
                compare: {speakers: {FL: {actual: {x_m: 1.0, y_m: 0.6, z_m: 1.0}, delta: {status: 'close', dist_m: 0.3}}}}};
              const pl = v3Placement(p, {speakers: {}}), sc = v3Scene({room: rm, seats: [{x_m: 2, y_m: 4}], subs: {}, furniture: []}, pl.spk, null, pl.lines);
              const tfl = sc.marks.find(m => m.label === 'TFL'); return pl.lines.length === 3 && pl.spk.length === 3 && !!tfl && Math.abs(tfl.boxes[0].z1 - 2.0) < 1e-6; })()"""))

            # ---- Turning the room: Mirror and Undo change the stored room and the form
            before = page.evaluate("S.room.furniture[1].x_m")
            page.click("#roTurn [data-op='cw']")
            check("Turn right: the room's size swaps in the form", until(page, "document.querySelector('#rL').value == '13'"))
            page.click("#roUndo")
            check("Undo turn: the size comes back", until(page, "document.querySelector('#rL').value == '20'"))
            check("Turn and undo leave the furniture where it was", abs(page.evaluate("S.room.furniture[1].x_m") - before) < 0.01)

            # ---- Subs page: Save subs stores through the same save
            page.goto(base + "/#/subs")
            page.wait_for_timeout(500)
            page.click("#subsSave")
            check("Subs: Save subs answers", until(page, "document.querySelector('#subsMsg').textContent === 'Saved.'"))

            # ---- Backups: make, list, delete, options
            page.goto(base + "/#/backups")
            page.wait_for_timeout(600)
            page.click("#bkMake")
            check("Backups: Back up now adds a row", until(page, "document.querySelectorAll('#bkOut tbody tr').length === 1"))
            page.click("#bkMake")
            check("Backups: a second backup adds another", until(page, "document.querySelectorAll('#bkOut tbody tr').length === 2"))
            page.locator("#bkOut [data-bkdel]").first.click()
            check("Backups: Delete removes the row", until(page, "document.querySelectorAll('#bkOut tbody tr').length === 1"))
            check("Backups: the list says what the room holds", "screen" in page.inner_text("#bkOut"))
            page.locator("#bkCard details summary").first.click()                  # the options are inside a closed section
            page.uncheck("#bkWeekly"); page.click("#bkSave")
            check("Backups: Save options answers", until(page, "document.querySelector('#bkMsg').textContent === 'Saved.'"))

            # ---- Basic and Advanced: the short menu, Show all pages, remembered, and the one-button first calibration
            page.evaluate("setMode('basic')")
            page.goto(base + "/#/home")
            page.wait_for_timeout(600)
            keys = lambda: page.evaluate("[...document.querySelectorAll('#sideNav button[data-k]')].map(b => b.dataset.k)")
            check("Basic: the menu is Home, Setup, Calibrate, Results, Compare", keys() == ["home", "setup", "wizard", "results", "ab"], str(keys()))
            check("Basic: advanced header items are hidden", page.is_hidden("#nightPill") and page.is_hidden("#mapCard"))
            page.click("#showAll")
            check("Show all pages switches to Advanced at once", until(page, "document.querySelectorAll('#sideNav button[data-k]').length > 20"))
            page.click("#uiModeSeg [data-uimode='basic']")
            page.reload()
            page.wait_for_timeout(1200)
            check("The chosen view is remembered after a reload", page.evaluate("uiMode") == "basic")
            check("Quick start card shows when nothing is calibrated", page.is_visible("#qsCard"))
            sent = []
            page.route("**/api/auto/start", lambda r: (sent.append(r.request.post_data), r.fulfill(status=200, content_type="application/json", body="{}")))
            if page.is_enabled("#qsGo"):
                page.click("#qsGo")
                check("Calibrate my subs starts a one-seat auto-tune", until(page, "true") and bool(sent) and '"seats":1' in sent[0], str(sent))
            else:
                check("Calibrate my subs is held back until the system is ready", "Not ready" in page.inner_text("#rdOut") or page.is_disabled("#qsGo"))
            page.click("#uiModeSeg [data-uimode='advanced']")

            # ---- Not on a Pi: the receiver test pages never talk about "the Pi" (this check runs on a PC or a CI machine)
            if page.evaluate("!S.host.pi"):
                import re as _re
                for key in ("blend", "allspk", "report", "liveeq"):
                    page.evaluate(f"openSheet('{key}')")
                    page.wait_for_timeout(500)
                    txt = page.inner_text("#viewBody")
                    check(f"No Pi wording on {key} when this is not a Pi", not _re.search(r"Pi", txt), str(_re.findall(r".{20}Pi.{20}", txt))[:200])
                page.evaluate("openSheet('home')")

            # ---- Data that changes behind the page's back reaches the page by itself (the page polls)
            page.goto(base + "/#/allspk")
            page.wait_for_timeout(600)
            grid = [20 * 2 ** (i / 12) for i in range(106)]

            def spk(name, lv, ms):
                return {"name": name, "heard": True, "level_db": 70 + lv, "bass_db": 60, "arrival_ms": ms, "level_vs_fl_db": lv, "arrival_vs_fl_ms": ms,
                        "distance_vs_fl_cm": round(ms / 1000 * 34300), "curve": [0.0] * len(grid)}

            def put(level, t):
                st = json.loads((data / "state.json").read_text()) if (data / "state.json").exists() else {}
                st["allspk"] = {"1": {"t": t, "pos": 1, "mode": "hdmi", "grid2": grid, "advice": [{"ch": "", "status": "good", "text": "ok"}],
                                      "speakers": {"FL": spk("Front left", 0, 0), "SL": spk("Surround left", level, 1.2), "LFE": spk("LFE", 0, 0)}}}
                (data / "state.json").write_text(json.dumps(st))

            put(-3.0, 1800000000.0)
            check("A new all-speakers result appears on its own", until(page, "document.querySelector('#chSheet') && document.querySelector('#chSheet').textContent.includes('+3.0 dB')", 6000))
            put(-6.0, 1800000100.0)
            check("A newer result replaces it on its own", until(page, "document.querySelector('#chSheet').textContent.includes('check wiring')", 6000))
            st = json.loads((data / "state.json").read_text())
            st["gain_check"] = {"status": "fix", "text": "TEST: the input would clip", "headroom_db": -2.0, "t": time.time()}
            st["busy"] = False
            (data / "state.json").write_text(json.dumps(st))
            check("State written behind the page's back reaches S", until(page, "S.gain_check && S.gain_check.text.startsWith('TEST')", 4000))

            # ---- AI suggestions are folded until opened, and stay as the owner left them
            st = json.loads((data / "state.json").read_text())
            st["suggestion"] = {"t": 1800000000.0, "had_measurements": True, "suggestion": {
                "goal_summary": "Movies", "confidence": "medium", "strategy": "Use both subs.", "avr": "", "cautions": ["Watch the clip"],
                "dsp_target": {"fmin": 18, "fmax": 120, "house_db": 5, "house_fc": 40, "max_boost_db": 3, "why": "A lift below 40 Hz."},
                "subs": [{"output": 1, "role": "Main", "gain": "g", "phase": "0", "low_pass": "off", "tuning_mode": "max", "other_controls": "o", "placement": "front", "why": "because"}]}}
            st["analysis"] = {"t": 1800000100.0, "source": "test", "markdown": "## Summary\n- one finding", "question": ""}
            (data / "state.json").write_text(json.dumps(st))
            sj = json.loads((data / "settings.json").read_text()) if (data / "settings.json").exists() else {}      # keep the accepted terms
            sj["subs"] = [0]
            (data / "settings.json").write_text(json.dumps(sj))
            page.evaluate("openSheet('subs')")
            check("AI setup suggestion appears folded", until(page, "document.querySelectorAll('#subsCard details.aifold').length >= 1", 8000)
                  and page.evaluate("[...document.querySelectorAll('#subsCard details.aifold')].every(d => !d.open)"),
                  "no folded suggestion on the Subs page")
            page.locator("#sugBox details.aifold > summary").scroll_into_view_if_needed()
            page.locator("#sugBox details.aifold > summary").click(timeout=8000)
            check("Opening it shows the suggestion", until(page, "document.querySelector('#sugBox details.aifold').open && document.querySelector('#sugBox').textContent.includes('Use both subs')"))
            page.evaluate("poll()")
            page.wait_for_timeout(1500)
            check("It stays open through a refresh", page.evaluate("document.querySelector('#sugBox details.aifold').open"))
            page.evaluate("openSheet('ai')")
            page.wait_for_timeout(600)
            check("The AI analysis is folded by default", page.evaluate("(() => { const d = document.querySelector('#aiOut details.aifold'); return !!d && !d.open; })()"))
            check("The assistant settings are folded too", page.evaluate("[...document.querySelectorAll('#aiQ ~ details.fold, details.fold')].some(d => !d.open)"))
            page.evaluate("openSheet('home')")

            check("No script errors while clicking around", not errs, "; ".join(errs[:3]))
            browser.close()
    finally:
        server.kill()
    if PROBLEMS:
        sys.exit("FAILED: " + "; ".join(PROBLEMS))
    print("\nEvery button checked updates the page by itself.")


if __name__ == "__main__":
    main()
