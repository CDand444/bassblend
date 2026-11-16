# Spec 09: speaker placement "delta" picture

**Goal:** on the Speaker placement page, show where each of the owner's speakers really is next to where Dolby's guideline says it should be, with a clear picture of the gap and plain numbers.

**Today:** the page (`renderPlacement` in `subtune/web/js/measure.js`) draws only the recommended spots from `layout.plan`. The owner's recorded positions (`room["speakers"][ch]` with `x_m, y_m, z_m`, entered on the Speakers page) are not shown there.

## Behavior

1. For every speaker in the plan that the owner has a recorded position for, the plan view draws the real speaker (filled circle, with its channel label), the recommended spot (hollow circle), and an arrow from real to recommended. Speakers with no recorded position show only the recommended spot, as now. A recorded speaker that the plan does not list (for example a channel the layout does not use) is drawn as a gray dot labeled "not in your layout".
2. A color for each pair by how far off it is: within 0.3 m (1 ft) or inside Dolby's angle range = good; within 0.8 m or 8 degrees of the range = meh; farther = off. The color is never the only sign: the row also says "OK", "close" or "off".
3. The table gains columns: **Yours** (from left / from front / height in ft), **Move** (for example "0.8 ft toward the screen, 1.2 ft right, 0.5 ft up", plain words), **Angle now** vs **Dolby range**, and a status. Sorted as in the plan. A short summary sentence above: "5 of 7 speakers are within Dolby's range; the biggest gap is SL (2.1 ft)."
4. Height speakers compare elevation (degrees up from the seat) the same way; ear-level speakers compare azimuth.
5. Nothing is written or changed; this is a view. No sound.

## Where

- `subtune/layout.py`: new pure function `compare(room: dict, plan: dict) -> dict` returning, per plan speaker, `actual` ({x_m, y_m, z_m, azimuth|elevation} or None) and `delta` ({dx_m, dy_m, dz_m, dist_m, angle_off_deg, in_range, status: "ok"|"close"|"off"}), plus `extra` (recorded speakers not in the plan) and `summary` text. Use the same azimuth/elevation conventions `plan()` already uses. Do not change `plan()`'s existing output keys.
- `subtune/server.py`: wherever `S.placement` is built into the state (grep `layout.plan` where it is added to the state), also attach the comparison under `placement["compare"]`.
- `subtune/web/js/measure.js` (`renderPlacement`): draw and tabulate as above. New top-level JS names start with `pd`.
- `subtune/web/manual.html`: a short paragraph in the speaker placement section.
- Tests: `tests/test_layout_compare.py` (offline): a speaker exactly on the plan is ok with dist 0; one 0.5 m off is close with the right dx/dy; one 2 m off is off; a height speaker compares elevation; a speaker without a position has actual None and no delta; extra recorded channels are listed; old plans without `compare` still render (JS must handle `compare` missing).

## Steps (one local-model session each)

1. `layout.compare` + tests (no server or page changes).
2. Server attach + page drawing/table + manual; manager runs the browser check.

## Out of scope

Moving speakers from this page, suggesting a new placement from the delta, measuring speaker position with the mic.
