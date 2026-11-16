# Spec 08: couches and sofas in the room

**Goal:** the owner can add couches/sofas to the room (length, depth, seat and back height, fabric), place them on the plan, and htTamer counts them in what it works out about the room: how much sound they absorb, where the listener's head is relative to the couch back, and what that means for the treatment plan. They are drawn in the 2D/3D room view.

**Why:** a couch is the biggest soft object in most home theaters. It changes the ring time, it sits against the back wall (the spot where bass piles up), and its back reflects sound to the listener's ears. Today none of it is known.

## What a couch is (data)

`room["furniture"]` = list of items, each `{id, kind: "couch", name, x_m, y_m, length_m, depth_m, seat_h_m, back_h_m, fabric, rotation: 0|90|180|270, against_wall: "front|back|left|right"|null, notes}`. x_m, y_m are the center of the footprint in the room frame (same as seats). Limits: length 0.6-4.5 m, depth 0.6-1.4 m, seat_h 0.3-0.6 m, back_h 0.6-1.3 m. Up to 12 items. Cleaned and validated in a new `subtune/furniture.py`.

Fabrics (a table in furniture.py, absorption coefficient per octave 125, 250, 500, 1k, 2k, 4k Hz, per square meter of the couch's surface area; typical published values, labeled as rough): `microfiber`, `fabric` (woven), `velvet`, `leather`, `vinyl`, `linen`. Leather and vinyl absorb the least, velvet and thick fabric the most. An unknown fabric falls back to `fabric`.

## What is calculated (furniture.py, pure functions)

1. `absorption(item)` -> sabins (m2) per octave: surface area (seat top + front + back + two arms, approximated from length, depth, heights) times the fabric's coefficients.
2. `room_rt60(room)` -> estimated RT60 per octave for the room by the Sabine formula, with the walls/floor/ceiling at conservative default coefficients (read `construction` text only for drywall/concrete/wood hints; otherwise use drywall) plus the furniture's sabins. Always labeled "estimate before you measure". When a measured RT60 exists, the measured one wins and the estimate is not shown.
3. `couch_back_gap(room, seat)` -> distance from the seat (listener head) to the couch back and to the wall behind, and whether a couch back at ear height (back_h_m above 0.9 m) sits within 1 m of the head (a reflection note: "couch back reflects at the ears").
4. A couch against the back wall counts as partial absorption for the rear-wall treatment item: if the couch back is over 1.0 m high and covers over 60 percent of the wall's length, the plan's "rear_wall" item is down-ranked with a plain note, never removed; bass behavior is not changed (a couch does not absorb bass; say so in the text).

## Where it plugs in

- Storage: `subtune/room.py` EMPTY gets `"furniture": []`; `save_room` runs `furniture.clean_items` (so old rooms keep working). Spec 06's `orient.py` must turn the items with the room (x_m, y_m, rotation, against_wall); add that to `orient.transform_room`.
- Treatment: `treatment.plan` uses `room_rt60` (when nothing is measured) and the back-wall/gap rules above; the plan's notes say where a couch is counted.
- Page: a "Furniture" block on Room and subs: add a couch (preset sizes: loveseat 1.6 m, 3-seat 2.2 m, sectional 2.8 m, recliner 1.0 m, custom), edit length/depth/heights/fabric, delete, and drag on the plan if the plan already supports dragging seats (follow spec 03 if it has landed, else numeric x/y fields plus "against back wall" button).
- Drawing: the 2D plan shows the footprint with the back edge thicker; `room3d.js` draws a simple box seat + back. New top-level JS names start with `fu`.
- Assistant: no change in this spec.
- Manual: a short section "Couches and furniture".

## Steps (one local-model session each; the manager runs the checks)

1. `furniture.py` + `tests/test_furniture.py`: clean_items, fabrics, absorption, room_rt60, couch_back_gap.
2. Wire room.py (storage, save), `orient.py` (turn furniture) and `treatment.py` (estimate, back-wall rule) + tests.
3. The page block (add/edit/delete) and the 2D drawing; `room3d.js` box drawing; manual.

## Done when

Offline tests cover: limits clamp, an unknown fabric falls back, leather absorbs less than velvet, more couch means a lower RT60 estimate, an item with a bad rotation is rejected, a couch against the back wall changes the rear-wall rank but not the item's existence, old rooms without `furniture` load unchanged, orient turns the couches with the room. `tests/test_js_globals.py` and the browser check pass.

## Out of scope

Bass/modal effects of furniture (small; do not model), other furniture kinds (they are a later `kind`), measuring a couch's absorption from a sweep.
