# Spec 06: rotate the room's orientation

**Goal:** the owner can choose which wall is the screen (front) wall, turn the room by quarter turns, or mirror it, and the whole plan turns with it. The outline, openings, seats, subs, speakers and the ceiling slope all keep their real places in the room. Nothing has to be re-entered or moved by hand; only the frame of reference (x from the left wall, y from the front wall) changes.

**Why:** rooms are often drawn with the screen on the wrong wall, or with length and width swapped. Today the only fix is to re-enter every position.

**Reading of the request:** "rotate the orientation to align the room without moving the speakers" is taken to mean the speakers stay where they physically are in the room. If the owner instead wants the outline moved underneath fixed coordinates, that is a different feature ("shift the room") and is not part of this spec.

## Behavior

1. **Controls** next to the room plan on Room and subs: Rotate left, Rotate right, Mirror left-right, and **Screen wall**: click a wall on the plan to make it the front wall (axis-aligned walls only in this version; for an angled wall say so in plain English). The plan view updates at once. An Undo button keeps the last 10 operations.
2. **The transform** (meters; W and L are the outline's width and length in the current frame; x is from the left wall, y from the front wall):
   - rotate clockwise: `(x, y) -> (L - y, x)`, and W and L swap
   - rotate counterclockwise: `(x, y) -> (y, W - x)`, and W and L swap
   - rotate 180 degrees: `(x, y) -> (W - x, L - y)`
   - mirror left-right: `(x, y) -> (W - x, y)`; this reverses the outline's point order, so edge numbers and opening distances flip with it
   - heights (`z`) never change.
3. **Everything that has a place or a direction is transformed together:**
   - the outline points and the Length and Width values (a plain rectangle just swaps them on a quarter turn);
   - `wall_openings` (they stay on the same physical wall: re-number the edges, and for a mirror measure `from_m` from the other end);
   - the ceiling: `low_side` front/back/left/right and the vault `ridge` length/width map to the new walls;
   - seats, subs and speakers (`x_m`, `y_m`; read `subtune/room.py` and `subtune/equip.py` for how they are stored), and any stored aim or facing direction;
   - treatment constraints that name a wall (front/back/left/right) and installed treatment items.
   Suggested speaker spots are computed from the room, not stored, so they follow automatically.
4. **Atomic and reversible:** all of it succeeds or nothing changes. Applying an operation and then its inverse restores the exact original; four quarter turns in one direction restore it.
5. If a saved result, report or tune stores any room coordinates, list where in your report and leave it alone; don't guess.

## Files

- New `subtune/orient.py` (under 300 lines): pure functions, no file or network access, e.g. `transform_room(room: dict, op: str, wall: int | None = None) -> dict` and `inverse(op)`. Use the existing `shape.py` helpers (`edges`, `clean_outline`, extent) instead of re-deriving geometry.
- Endpoint `POST /api/room/orient` with `{op: "cw" | "ccw" | "180" | "mirror" | "screen_wall", wall: <edge index>}`: validate, run `transform_room`, save through the same path as other room edits (so validation and the journal entry happen), return the new room. It sits behind the sign-in and the terms gate like any action.
- Page: the buttons and the click-a-wall mode in the plan code (`room-ai.js` or the new drawing script if spec 03 has landed). New top-level names start with `ro`. Highlight walls on hover in screen-wall mode.
- `subtune/web/manual.html`: a short section on orientation, in "Rooms that aren't boxes".

## Done when

- Tests in `tests/test_orient.py` (offline, temp data folders):
  - four clockwise quarter turns return the original room exactly; clockwise then counterclockwise too; mirror twice too;
  - after any operation, every seat, sub and speaker is still the same distance from the same physical wall (compute the distance to each outline edge before and after and compare);
  - an L-shaped room with a door and a window keeps each opening on the same physical wall, at the same spot along it;
  - the ceiling `low_side` and `ridge` follow the rotation (check one case per direction);
  - everything stays inside the outline;
  - the endpoint rejects a bad `op` or an out-of-range `wall` and changes nothing.
- `python tests/test_compile.py`, `python -m pyflakes subtune/` and `python tests/test_js_globals.py` pass; the manager runs the whole suite and the browser check.

## Out of scope

Free-angle rotation, shifting the outline underneath fixed coordinates, the 3D view's camera, the phone room builder.
