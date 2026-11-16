# Spec 07: the every-channel report and receiver setup sheet

**Goal:** after the all-speakers check, the owner gets a channel-by-channel report (every speaker the check can measure) and a **receiver setup sheet**: for each channel, what to change in the receiver (level trim and distance), with the final numbers when the current settings are known. It can be printed and copied.

**Why:** the all-speakers check already measures every bed speaker against the front left and gives one-line tips, but there is no single sheet to work from, no tonal comparison between channels, no bass extension per speaker, and the tips can go stale when the owner changes a receiver setting after the measurement. See `docs/dev/ROADMAP.md`, section E, item 1.

## What exists (read these first)

- `subtune/allspk.py`: `analyse()` returns `{"t", "grid2", "speakers": {ch: {...}}, "advice"}`. Per speaker (`ch` is FL, FR, C, SL, SR, SBL, SBR, LFE): `name`, `level_db` (mean 500-2000 Hz; for LFE 30-80 Hz), `bass_db`, `arrival_ms`, `heard`, `snr_x`, `curve` (response in dB relative to its own mid band, on `grid2`), `level_vs_fl_db`, `arrival_vs_fl_ms`, `distance_vs_fl_cm`. `advice()` already turns these into tips (level change = minus `level_vs_fl_db`; "later than the front left" means increase its distance by `arrival_vs_fl_ms` x 0.343 m; more than 4 dB or 5 ms off means "check wiring", not a setting) and `lfe_check()` expects the LFE channel at +10 dB.
- The latest result is in the state under `allspk` (keyed by mic spot; the newest by `t` is used, see `subtune/server.py`, `overview()`).
- `subtune/equip.py`: speaker records per channel with `rx_level_db`, `rx_distance_m` (copied by the owner from the receiver's menu; the receiver cannot report them over the network), `size`, `crossover_hz`, `x_m`, `y_m`, `z_m`, `kind`, `model`. `subtune/dirac.py` `system()` has the layout and whether Dirac is on.
- Heights (`TFL`, `TFR`, `TML`, `TMR`, `TRL`, `TRR`) and wides can't be reached with the 7.1 test file, so they are **not measured**.
- `subtune/report.py` builds the printable calibration report served at `/report`; copy its page style.

## The report (per channel)

For each channel row show: name, heard (yes/no), level vs the front left (dB), arrival vs the front left (ms and feet), **tonal match to the front left** and **bass extension**:
- Tonal match: the rms difference in dB between the channel's `curve` and the front left's `curve` over 200 Hz to 8 kHz (use `grid2`; the front left itself shows "reference"). Defaults: under 2 dB good, 2 to 4 watch, over 4 fix. Keep these as named constants.
- Bass extension: the lowest frequency at which `curve` is still within 3 dB (F3) and 6 dB (F6) of its mid band, searching down from 150 Hz. Show it as information only (the crossover recommendation is a later spec). If the curve never reaches below 3 dB in range, show "below 20 Hz".
- Heights and wides: a row saying "not measured: needs Dolby Atmos content; use the receiver's own calibration" plus the position and recommended placement if recorded.
- The LFE row uses `lfe_check()`'s verdict.

## The receiver setup sheet

One table, ordered like a receiver's menu (front, center, surrounds, surround backs, then the subwoofer level), with these columns:
- **Level change (dB):** minus `level_vs_fl_db`, rounded to 0.5 dB, capped at plus or minus 12 dB. A larger need means "check wiring or assignment first" (reuse the existing `odd` rule), not a number.
- **Distance change (ft):** `arrival_vs_fl_ms` x 0.343 m converted to feet, rounded to 0.1 ft; later means increase.
- **Now** and **Set to:** when the speaker record has `rx_level_db` / `rx_distance_m` (copied from the receiver), show the current value and the result of applying the change. Otherwise show only the change and the note "enter your current values on the Speakers page to see the final numbers".
- A channel within 1 dB and 0.3 ms of the front left shows "no change".
- Receiver menu wording comes from one small table `MENU_WORDS` keyed by receiver make (settings `avr_make`), with a generic fallback ("Level Calibration", "Distance"); keep it data-driven so the owner can correct it. Don't invent exact menu paths for makes you don't know.
- If Dirac is on (`dirac.system()`), print "Dirac sets levels and distances: use this sheet to verify, not to change" instead of change instructions.

## Measured, not current (important)

Advice must use the settings that were in effect **when the measurement was taken**, never today's. So `allspk.run` stores, with the result, a snapshot `rx_at_measure`: `{ch: {"level_db", "distance_m"}}` taken from the speaker records at that moment (the values may be missing). The sheet's "Now" column uses that snapshot; if today's speaker records differ from it, show a clear warning: "Receiver settings changed since this measurement: run the speaker check again before applying these numbers."

## Files

- New `subtune/channels.py` (under 350 lines): `build(result, speakers, system, make, rx_at_measure=None, now_speakers=None) -> dict` (rows, sheet, warnings; pure, no file or network access), `sheet_html(...)` for the printable page, `MENU_WORDS`, the named constants.
- `subtune/allspk.py`: store `rx_at_measure` in the result (small change in `run`).
- Endpoints in the existing routes: `GET /api/channels` (JSON of `build(...)` for the newest result) and `GET /channels` (the printable page). Behind the sign-in like other pages.
- Page: a "Receiver setup sheet" section under the results on the Speaker check page (`#allCard`, code in `subtune/web/js/measure.js`), with Copy and Print buttons. New top-level names start with `ch`.
- `subtune/server.py` `overview()`: add the sheet rows to `all_speakers_check` so the assistant can use them; one sentence in the assistant prompt (`subtune/assistant.py`).
- `subtune/report.py`: add a "Channel by channel" section to the calibration report.
- `subtune/web/manual.html`: a section "Every-channel report and receiver setup sheet".

## Steps (one task each, landed in order)

1. `subtune/channels.py` with its tests (no page, no endpoint).
2. Snapshot in `allspk.run`, the two endpoints, the stale-settings warning.
3. The page section, the assistant overview entry and prompt sentence, the manual.
4. The calibration report section.

## Done when (each step)

- `tests/test_channels.py` (offline; build realistic `allspk.analyse` result dicts by hand or with `allspk.analyse` on synthetic recordings as `tests/test_allspk.py` does):
  - a speaker 3 dB quieter and 1.2 ms later than the front left gives "+3.0 dB" and "increase by 1.3 ft" (check the arithmetic against the existing `advice()` text so they agree);
  - rounding to 0.5 dB and 0.1 ft; a trim beyond 12 dB or a speaker 6 ms early gives the "check wiring" row, not a number;
  - "Now" and "Set to" appear only when the speaker record has the values, and use `rx_at_measure`, not today's records; a changed record produces the stale warning;
  - Dirac on produces the verify-only wording; heights and wides are listed as not measured;
  - tonal match and F3/F6 are right on synthetic curves (a flat curve, a curve rolling off at 60 Hz);
  - the printable page escapes text and contains every channel.
- `python tests/test_compile.py`, `python -m pyflakes subtune/`, `python tests/test_js_globals.py` pass; the manager runs the whole suite and the browser check.

## Out of scope

Choosing the crossover (a later spec), measuring heights or wides, changing any receiver setting automatically, Dirac.
