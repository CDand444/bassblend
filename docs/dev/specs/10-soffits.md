# Spec 10: soffits (bulkheads, drop ceilings) on the floor plan

**Goal:** the owner can add soffits to the room: a box or drop along a wall that lowers the ceiling there (very common around a home theater's screen wall, side walls, or around ducts). The floor plan draws them, and what htTamer works out about heights uses them.

## Data

`room["room"]["soffits"]` = list (max 12) of `{id, name, wall, from_m, length_m, depth_m, bottom_m}`: sits on outline edge `wall` (same numbering and `from_m` rule as `wall_openings`: edge i runs from corner i to i+1, `from_m` along it), is `length_m` long along the wall, projects `depth_m` into the room (0.1-2.0), and its underside is `bottom_m` above the floor (1.8 up to the ceiling height minus 0.05). Cleaned and validated in `subtune/shape.py` (`clean_soffits`, next to `clean_openings`), saved through `room.save_room` / `clean_shape`, old rooms without the key load unchanged. A soffit that overhangs the end of its wall is rejected with a plain message.

## What it changes

1. **Drawing:** the 2D plan draws each soffit as a hatched rectangle on its wall (depth to scale) with a small label ("soffit, 2.2 m high"); `subtune/web/js/room3d.js` draws it as a box under the ceiling.
2. **Ceiling height at a point:** `shape.ceiling_z(rm, x, y)` returns the soffit's `bottom_m` when the point is under a soffit (the lowest of ceiling and soffit). Everything that already uses it follows: height-speaker spots in `layout.py` (a height speaker over a soffit sits at the soffit underside), room-height numbers shown to the owner.
3. **Treatment:** the ceiling-reflection points and "ceiling cloud" zone in `treatment.py` use the real ceiling height at the reflection point; when a soffit runs along the front wall, add one plain note: "A soffit along the front wall: in-ceiling or height speakers there are close to the wall; treat the soffit underside like a ceiling reflection point". Do not change bass/mode numbers: the volume is small and the modal report stays on the main box; the manual says so.
4. **Orientation (spec 06):** `orient.py` turns soffits like wall openings (renumber `wall`, mirror flips `from_m`; depth and heights unchanged).
5. **Page:** a "Soffits" list in the Room and subs shape block next to openings: wall (numbered like the corners, same dropdown the openings use), from, length, depth, underside height; add/delete. Feet or meters like the rest of the page.
6. **Manual:** a short paragraph in "Rooms that aren't boxes".

## Steps (one local-model session each)

1. `shape.py` helpers (`soffits`, `clean_soffits`, soffit-aware `ceiling_z`, `room.py` save) + `tests/test_soffits.py` (limits, overhang rejected, ceiling_z under/not under, old rooms load, wall renumbering unaffected).
2. `orient.py` + `layout.py` / `treatment.py` hooks + tests (height speaker over a soffit sits at its underside; orient turns soffits; the front-wall note appears only with a front soffit).
3. Page editor, 2D drawing and `room3d.js` box, manual; manager runs the browser check.

## Out of scope

Free-standing drop panels in the middle of the room (clouds are a treatment item), soffit materials and absorption, bass effect of the soffit.
