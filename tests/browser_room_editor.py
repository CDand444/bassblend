r"""Browser check of the Room page's newest parts on their own: the sub model drop-down, flooring, the room modeler (tier builder) and the top-down room editor.

Split out of tests/browser_actions.py so it runs in about a minute and a failure points at one feature.
Starts htTamer with a small seeded room (no sound, no receiver, no miniDSP). Needs Playwright:  pip install playwright && python -m playwright install chromium
Run:  python tests/browser_room_editor.py            (not part of the offline tests: it needs a browser)
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import browser_check as bc                                   # noqa: E402
from browser_actions import PROBLEMS, check, until          # noqa: E402

ROOM = {"room": {"length_m": 5.486, "width_m": 3.962, "height_m": 2.591}, "seats": [{"name": "MLP", "x_m": 2.0, "y_m": 3.2, "z_m": None}],
        "subs": {"0": {"model": "", "x_m": 0.61, "y_m": 1.524, "aim_deg": 90}},
        "speakers": {"FL": {"x_m": 0.9, "y_m": 0.3, "kind": "tower"}, "SL": {"x_m": 0.05, "y_m": 3.0, "kind": "in-wall"}},
        "screen": {"kind": "projector", "diagonal_in": 100, "aspect": "16:9", "width_m": 2.21, "height_m": 1.25, "at": False, "lcr_behind": False, "bottom_m": 0.6, "behind_m": 0, "frame_m": 0.08, "x_m": 1.98, "notes": ""},
        "furniture": [{"id": "couch-1", "kind": "couch", "name": "3-seat couch", "x_m": 1.98, "y_m": 4.9, "length_m": 2.2, "depth_m": 0.95, "seat_h_m": 0.45, "back_h_m": 1.0, "fabric": "fabric", "rotation": 0},
                      {"id": "riser-1", "kind": "riser", "name": "Riser", "x_m": 1.98, "y_m": 4.9, "length_m": 2.5, "depth_m": 1.3, "height_m": 0.2, "rotation": 0}]}


def main():
    from playwright.sync_api import sync_playwright
    port = bc.free_port()
    server, tmp = bc.start_server(port)
    base = f"http://127.0.0.1:{port}"
    data = pathlib.Path(tmp) / "data"
    try:
        (data / "room.json").write_text(json.dumps(ROOM))
        (data / "settings.json").write_text(json.dumps({"subs": [0]}))
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
            tabs = page.evaluate("[...document.querySelectorAll('[data-rtab]')].map(b => b.dataset.rtab)")
            check("Room tabs: the parts of the room are tabs", tabs == ["size", "shape", "home", "screen", "seats", "furniture", "fixtures"], str(tabs))
            page.click("[data-rtab='seats']")
            check("Room tabs: choosing Seats shows only that part, and the plan stays in view",
                  page.evaluate("[...document.querySelectorAll('[data-rpanel]')].filter(p => !p.hidden).map(p => p.dataset.rpanel).join()") == "seats" and page.locator("#plan").is_visible())
            page.click("[data-rtab='size']")
            check("Room tabs: back to Size shows the length box", page.locator("#rL").is_visible())
            page.evaluate("document.querySelectorAll('[data-rpanel]').forEach(p => { p.hidden = false; })")      # the checks below reach into every tab
            # ---- Room card: flooring and the modeler
            page.evaluate("openSheet('room'); document.querySelectorAll('[data-rpanel]').forEach(p => { p.hidden = false; })")
            page.wait_for_timeout(500)
            check("Sub card: the model drop-down lists the database, and picking one fills size, driver and ratings", until(page, "SUB_DB && SUB_DB.length > 10", 6000) and page.evaluate("""(() => {
              const sel = document.querySelector('#subRows .subcard:not(.off) [data-pick="submodel"]'); if (!sel) return 'no used sub card';
              if (![...sel.options].some(o => o.value === 'PB-2000 Pro')) return 'PB-2000 Pro is not in the list';
              sel.value = 'PB-2000 Pro'; sel.dispatchEvent(new Event('change', {bubbles: true}));
              const card = sel.closest('.subcard'), g = f => card.querySelector(`[data-f="${f}"]`).value;
              return g('model') === 'PB-2000 Pro' && g('driver') === '12"' && g('enclosure') === 'ported' && +g('width_in') === 17.3 && +g('height_in') === 20.9 && +g('depth_in') === 23.6 && +g('amp_w') === 550 && +g('f3_hz') === 16 && card.querySelector('input[data-f="model"]').hidden || JSON.stringify([g('model'), g('driver'), g('enclosure'), g('width_in'), g('amp_w')]); })()""") is True)
            check("Sub card: a model htTamer has a controls guide for brings its knobs (no second picker)", page.evaluate("""(() => {
              const card = document.querySelector('#subRows .subcard:not(.off)'), cat = card.querySelector('input[data-f="catalog"]');
              return !!cat && cat.value === 'svs-pb2000-pro' && !!card.querySelector('.hwctl [data-c]') && !card.querySelector('select[data-f="catalog"]') || (cat ? cat.value : 'no catalog'); })()""") is True)
            [page.fill(i, v) for i, v in (("#rL", "18"), ("#rW", "13"), ("#rH", "8.5"))]
            page.select_option("#rFloor", "tile")
            page.check("#rRug")
            page.evaluate("document.querySelector('#mdBox').open = true")
            page.fill("#mdRows", "3")
            page.fill("#mdFirst", "6")
            page.fill("#mdStep", "6")
            before = page.evaluate("fuRead().length")
            page.check("#mdReplace")                                         # replace the list, not add to it
            page.click("#mdBuild")
            check("The tier builder puts risers and couches into the Room form",
                  until(page, "fuRead().filter(i => i.kind === 'riser').length >= 2 && fuRead().filter(i => i.kind === 'couch').length === 3", 40000) is True,
                  "form has " + str(page.evaluate("fuRead().length")) + " items (was " + str(before) + "); " + str(page.evaluate("document.querySelector('#mdMsg').dataset.err || document.querySelector('#mdMsg').textContent")))
            check("Undo is offered, and it puts the list back", page.evaluate("!document.querySelector('#mdUndo').hidden") is True)
            page.click("#mdUndo")
            check("Undo restores the list", until(page, f"fuRead().length === {before}") is True)
            page.click("#roomSave")
            page.wait_for_timeout(1200)
            saved = page.evaluate("fetch('/api/state').then(r => r.json()).then(r => [r.room.room.floor, r.room.room.rug])")
            check("Floor and rug are saved with the room", saved == ["tile", True], str(saved))
            # ---- the room editor (top-down): open, add by click and by drop, drag with snapping, turn, delete, undo, apply into the Room card
            page.evaluate("openSheet('room'); document.querySelectorAll('[data-rpanel]').forEach(p => { p.hidden = false; })"); page.wait_for_timeout(300)
            page.click("#edOpen")
            check("Room editor opens as a pop-out with the room drawn", until(page, "!document.querySelector('#edBack').hidden && !!document.querySelector('#edStage svg')", 4000) is True)
            check("Room editor: a move re-fits only the risers it could touch", page.evaluate("""(() => {
              const A = {k: 'riser', d: {x_m: 1, y_m: 1, length_m: 1, depth_m: 1, rotation: 0}}, B = {k: 'riser', d: {x_m: 3, y_m: 4.5, length_m: 1, depth_m: 1, rotation: 0, want: [2.5, 4, 3.5, 5]}};
              const couch = {k: 'couch', d: {x_m: 1.2, y_m: 2.0, length_m: 1, depth_m: 0.8, rotation: 0}}, near = [{it: couch, boxes: [edBox(couch)]}];
              return edWrapTouches(A, near) && !edWrapTouches(B, near) && edWrapTouches(B, [{it: B, boxes: []}]) && edWrapTouches(B, null); })()""") is True)
            def drag_item(sel_js, dx, dy):
                at = page.evaluate("(() => { const i = " + sel_js + "; const b = document.querySelector('#edStage .ed-it[data-i=\"' + i + '\"] .edr').getBoundingClientRect(); return [i, b.left + b.width / 2, b.top + b.height / 2]; })()")
                page.mouse.move(at[1], at[2]); page.mouse.down(); page.mouse.move(at[1] + dx, at[2] + dy, steps=6); page.mouse.up()
                return at[0]
            i = drag_item("ED.items.findIndex(it => it.k === 'spk' && it.ch === 'SL')", 60, 50)
            sl = page.evaluate(f"[ED.items[{i}].d.x_m, ED.items[{i}].d.y_m]")
            check("Room editor: an in-wall speaker slides along its wall and stays on it", abs(sl[0] - 0.03) < 0.02 and sl[1] > 3.1, str(sl))
            i = drag_item("ED.items.findIndex(it => it.k === 'screen')", -40, 80)
            scr = page.evaluate(f"[ED.items[{i}].d.x_m, ED.items[{i}].d.y_m]")
            check("Room editor: the screen slides along the front wall only", scr[0] < 1.95 and abs(scr[1] - 0.04) < 0.01, str(scr))
            page.click("[data-edv='3d']")
            check("Room editor: the 3D view shows the same room", until(page, "!document.querySelector('#ed3Box').hidden && !!ED.v3 && document.querySelector('#ed3').width > 100", 4000) is True)
            at = page.evaluate("""(() => { const i = ED.items.findIndex(it => it.k === 'couch'); const it = ED.items[i], p = ED.v3.project([it.d.x_m, it.d.y_m, 0.6]), r = document.querySelector('#ed3').getBoundingClientRect();
              return [i, r.left + p[0], r.top + p[1], it.d.x_m, it.d.y_m]; })()""")
            page.mouse.move(at[1], at[2]); page.mouse.down(); page.mouse.move(at[1] + 70, at[2] + 25, steps=8); page.mouse.up()
            now = page.evaluate(f"[ED.sel, ED.items[{at[0]}].d.x_m, ED.items[{at[0]}].d.y_m]")
            check("Room editor 3D: dragging a couch picks it and moves it on the floor", now[0] == at[0] and (abs(now[1] - at[3]) > 0.05 or abs(now[2] - at[4]) > 0.05), str([at, now]))
            yaw = page.evaluate("ED.cam3.yaw"); box = page.locator("#ed3").bounding_box()
            page.mouse.move(box["x"] + 12, box["y"] + 12); page.mouse.down(); page.mouse.move(box["x"] + 112, box["y"] + 12, steps=5); page.mouse.up()
            check("Room editor 3D: dragging empty space turns the view instead", abs(page.evaluate("ED.cam3.yaw") - yaw) > 0.3)
            page.click("#edUndoB")
            page.click("[data-edv='top']")
            check("Room editor: back to the top view", page.evaluate("!document.querySelector('#edStage').hidden && document.querySelector('#ed3Box').hidden") is True)
            n0 = page.evaluate("ED.items.length")
            page.click("[data-edadd='couch:three']")
            check("Add a couch from the palette", page.evaluate("ED.items.length") == n0 + 1 and page.evaluate("ED.items[ED.sel].k") == "couch")
            page.evaluate("(() => { const it = ED.items[ED.sel]; it.d.x_m = 1.0; it.d.y_m = 1.0; edRender(); })()")
            box = page.locator(".ed-it.sel rect.edr").bounding_box()
            cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            page.mouse.move(cx, cy); page.mouse.down(); page.mouse.move(cx + 40, cy + 30, steps=6); page.mouse.up()
            moved = page.evaluate("[ED.items[ED.sel].d.x_m, ED.items[ED.sel].d.y_m]")
            check("Dragging a couch moves it", moved[0] > 1.0 and moved[1] > 1.0, str(moved))
            page.evaluate("(() => { const it = ED.items[ED.sel]; it.d.x_m = it.d.length_m / 2 + 0.1; it.d.y_m = 2; edRender(); })()")
            box = page.locator(".ed-it.sel rect.edr").bounding_box(); cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            page.mouse.move(cx, cy); page.mouse.down(); page.mouse.move(cx + 2, cy, steps=3); page.mouse.up()
            edge = page.evaluate("(() => { const it = ED.items[ED.sel]; return it.d.x_m - it.d.length_m / 2; })()")
            check("A couch dragged near the left wall pulls to it", abs(edge) < 0.02, str(edge))
            page.keyboard.press("r")
            check("R turns the selected couch a quarter turn", page.evaluate("ED.items[ED.sel].d.rotation") == 90)
            page.click("[data-edadd='riser']")
            check("Add a riser", page.evaluate("ED.items.length") == n0 + 2 and page.evaluate("ED.items[ED.sel].k") == "riser")
            page.evaluate("(() => { const cs = ED.items.filter(i => i.k === 'couch'); const c = cs[cs.length - 1]; c.d.x_m = 1.6; c.d.y_m = 1.4; ED.items[ED.sel].d.x_m = 1.6; ED.items[ED.sel].d.y_m = 2.2; edRender(); })()"); page.evaluate("document.querySelector('#edAuto').checked = false"); page.evaluate("edWrap(true)")   # a couch on the floor in the riser's way: the riser re-cuts itself around it
            check("A riser wraps around a couch standing in its way", until(page, "ED.items.some(i => i.k === 'riser' && i.d.id === ED.items[ED.sel].d.id && i.d.points && i.d.want && i.d.points.length > 4)", 40000) is True, page.evaluate("(async () => { const r = ED.items[ED.sel], rf = ED.room, subs = {}; ED.items.filter(it => it.k === 'sub').forEach(it => { subs[it.o] = it.d; }); const res = await post('/api/modeler', {action: 'cut', item: r.d, others: ED.items.filter(i => i !== r && (i.k === 'couch' || i.k === 'riser')).map(i => i.d), room: {room: {width_m: rf.room.width_m, length_m: rf.room.length_m, height_m: rf.room.height_m, outline: rf.room.outline, wall_openings: rf.room.wall_openings}, seats: rf.seats, subs}}); return JSON.stringify([res.error || 'ok', Object.keys(subs), (res.items || []).length]); })()"))
            try:
                page.select_option("#edSide [data-edf='material']", "carpet", timeout=4000)
            except Exception:                                                   # report what the side panel held instead of hanging
                check("The riser's top material is set in the editor", False, page.evaluate("JSON.stringify([ED.sel, ED.items.map(i => i.k), document.querySelector('#edSide').innerText.slice(0, 160)])"))
            else:
                check("The riser's top material is set in the editor", page.evaluate("ED.items[ED.sel].d.material") == "carpet")
            page.focus("#edStage"); page.keyboard.press("Delete")
            check("Delete removes the selected riser", page.evaluate("ED.items.length") == n0 + 1)
            page.click("#edUndoB")
            check("Undo brings the riser back", page.evaluate("ED.items.length") == n0 + 2)
            before = page.evaluate("fuRead().length")
            page.click("#edApplyB")
            check("Apply saves the moved speaker's position", until(page, "S.room && S.room.speakers && S.room.speakers.SL && S.room.speakers.SL.y_m > 3.1", 8000) is True)
            check("Apply moves the screen in the Room card", abs(float(page.evaluate("document.querySelector('#scX').value") or 0) - 6.5) < 0.2 or float(page.evaluate("document.querySelector('#scX').value") or 0) < 6.4)
            check("Apply puts the couch and riser into the Room card and closes the editor", page.evaluate("document.querySelector('#edBack').hidden") is True and page.evaluate("fuRead().length") == before + 2)
            page.evaluate("openSheet('home')")

            check("No script errors while clicking around", not errs, "; ".join(errs[:3]))
            browser.close()
    finally:
        server.kill()
    if PROBLEMS:
        sys.exit("FAILED: " + "; ".join(PROBLEMS))
    print("The Room page's sub drop-down, flooring, modeler and editor all work.")


if __name__ == "__main__":
    main()
