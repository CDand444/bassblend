# Spec 03: draw the room by dragging walls and corners

**Goal:** the owner can draw an unusual room directly on the plan: pull walls in and out, move corners, add and delete corners, with live sizes, undo, and a refusal of shapes that can't be a room.

**Why:** typing corners into a list was hard to use. The owner's screenshot shows a sliver triangle (3 corners, "4.1 x 19.5 ft") while the Length and Width boxes still said 19.5 x 12.8, and a 7 ft door on a 4 ft wall. They also had the **3D view** selected while editing, so nothing could be dragged. See `docs/dev/ROADMAP.md`, item 5.

## What exists (read these before changing anything)

In `subtune/web/js/room-ai.js`: `roomShape` (`{outline, shape, wall_openings, ceiling}`; outline = `[x, y]` points in metres, x from the left wall, y from the front wall), `renderPlan()` (draws the SVG into `#plan`; corner handles `.vh`, add-a-corner handles `.eh`, polygon `#roomPoly`), `renderShapeEditor()`, `setPts()`, `syncExtent()`, and the pointer handlers under the comment "dragging corners on the plan" (corner drag with 3 in. snap and square-wall snapping). In `subtune/shape.py`: `shape_problem(pts)` (why an outline can't be a room), `clean_outline`, `clean_openings`. The server also validates when saving (`room.clean_shape`).

## Behaviour

1. **Editing is on the 2D plan.** Starting to edit (picking a shape, dragging, adding a corner) switches to the 2D view automatically; 2D is the default view. The 3D view stays read-only.
2. **Bigger, easier handles:** corner handles at least 12 px (24 px hit area on touch); a wall highlights when the pointer is near it.
3. **Drag a wall** (press on the wall line): both end corners move together along the wall's perpendicular, keeping it parallel. Same snap (0.25 ft) and square-wall snapping as corners. This is how you make an alcove or an L.
4. **Drag a corner**, as now. **Add a corner** with the existing + handle or by double-clicking a wall. **Delete a corner** with a right-click/long-press or a small x on a selected corner. A room never has fewer than 4 corners: refuse and say why.
5. **Live sizes** while dragging: the lengths of the touched walls, and the overall width and length.
6. **Validation on release** with `shape_problem(pts)` rules mirrored in JS (`rdProblem(pts)`; keep both in step): crossing walls, a wall under 1 ft, area under 20 sq ft, needle-sharp angles. An invalid result reverts to the points before the drag and shows a one-line plain-English reason in `#roomMsg`.
7. **Openings stay valid:** after any change every opening fits its wall (clamp `from_m` and `width_m`); if its wall no longer exists, move it to the nearest wall.
8. **Length and Width boxes always show the outline's real extent;** typing in them scales the outline proportionally (and re-clamps openings).
9. **Undo/redo** (50 steps): Ctrl+Z, Ctrl+Shift+Z / Ctrl+Y outside text fields, plus two buttons. A "Back to rectangle" button.
10. Works with touch (Pointer Events, `touch-action: none` on handles) as well as the mouse. The corner list stays as an advanced option.

## Files

- Move the pointer-handler block out of `room-ai.js` into a new `subtune/web/js/room-draw.js`, loaded right after `room-ai.js` (add the `<script>` tag in `index.html` in that order). This also makes `room-ai.js` smaller.
- All new top-level names in it start with `rd`. Run `tests/test_js_globals.py`.
- Server side: only if `shape.py` needs a rule the JS mirrors; add its test to `tests/test_shape.py`.
- `subtune/web/manual.html`: update "Rooms that aren't boxes" (how to drag a wall, add and delete corners, undo).

## Tests

- Python: any new `shape.py` rule gets cases in `tests/test_shape.py`.
- Page: a Playwright check, `tests/browser_room_check.py` (same style as `tests/browser_check.py`: start the server on a free port with temp data, accept the terms, open `#/room`). It sets a rectangular room through page JS, drags a wall handle with the mouse, and asserts the outline changed by the dragged amount and the Length/Width boxes match; drags a corner into a crossing shape and asserts the reverted outline and the message; presses Ctrl+Z and asserts the undo.
- `tests/test_js_globals.py` and `tests/browser_check.py` still pass.

## Out of scope

Rotating or tilting walls freely (angles stay on the 15° grid unless a key is held), 3D editing, importing floor plans (the phone builder does that), the ceiling editor.
