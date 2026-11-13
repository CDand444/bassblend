# BassBlend changelog

## Nov 13, 2026 — first-boot setup in the browser (for a ready-made SD card)

- A fresh BassBlend in network mode (no PIN yet) shows a **setup guide** instead of the dashboard:
  1. choose a PIN, 2. add the mic calibration file, 3. find the receiver (automatic search, or by
  hand), 4. add the AI key (optional). Steps can be skipped or changed later; "Finish later and
  open BassBlend" lands on the Setup checklist.
- The first PIN can only be chosen once; after that the page needs signing in, and someone else
  on the network can't replace it. Until setup is finished, signed-in visits to the dashboard
  come back to the guide once.
- The Linux setup script no longer asks for a PIN in the terminal (`--pin` still does). This is
  what lets an SD card image need no terminal at all.
- Tested end to end on an isolated "fresh card" copy, with phone and dark layouts checked.
  12 checks in `tests/test_portable.py`.

## Nov 13, 2026 — ready for Linux / Raspberry Pi (silent)

- **git**: the project is now a git repository (nothing committed yet). Your `data/` folder and the
  downloaded `tools/` are excluded; shell scripts keep Unix line endings.
- **Runs on Windows or Linux** without changing settings:
  - audio devices are found by name on either system ("auto" audio system; old Windows settings still work on Linux);
  - the right minidsp-rs build is picked per system, and a USB address saved on Windows is ignored on Linux;
  - `BASSBLEND_DATA` and `BASSBLEND_CONFIG` move the data and the API key/PIN folder (used on the Pi);
  - a missing mic calibration file now shows in the Setup checklist and gives a clear message.
- **Network mode with a PIN**: `python -m subtune set-pin`, then `serve --lan`. Sign-in page, 30-day
  sessions, wrong-PIN lockout, HttpOnly SameSite cookies, a same-site check on every action, and
  "Sign out" in the menu. This PC's normal mode is unchanged (local only, no sign-in).
- **Linux setup script** `deploy/linux/install.sh` (normal and `--dev`), with a service, a USB
  permission rule and the minidsp-rs download. Guide: `docs/RASPBERRY_PI.md`.
- New offline tests: `tests/test_portable.py` (11 checks). Sign-in tested end to end on an isolated
  copy. Not yet run on a real Pi.

## Nov 13, 2026 — speaker layout and working alongside Dirac Live (silent)

- **Your speakers** (Receiver screen): choose the layout (set to 7.3.4), crossover, and whether you
  use Dirac Live and its Bass Control. BassBlend only uses this to guide you; it changes nothing in
  the receiver. Includes a "Receiver settings to check once" list built from the layout.
- **Dirac Live step in the wizard** (shown when you use Dirac): what to check first, a download of
  BassBlend's target as a Dirac target-curve file (Flat / Gentle / Warm treble, with a small graph),
  seven plain steps for running Dirac, and an "I've run Dirac Live" button.
- BassBlend remembers which sub tune Dirac was run with. A blend fix keeps it valid (it only shifts
  timing); a new sub tune asks you to run Dirac again. Marking Dirac as run clears older blend
  measurements, since the speakers then sound different.
- Setup checklist has a "Speakers and Dirac Live" line; the system map shows the layout and Dirac state.
- The assistant knows the layout, the Dirac order of steps, and that it can't operate Dirac itself.
- Fixes: the system map could show "Not set by BassBlend" until the slot names loaded.
- New offline tests: `tests/test_dirac.py` (6 checks: file layout, curve shape, layout names, when
  Dirac needs re-running). All 23 offline checks pass.
- Not verified: Dirac Live actually importing the file. Dirac publishes no format spec; the file
  follows the layout Dirac Live 2/3 files use.

## Nov 13, 2026 — left + right blend, interface polish (silent)

**Project moved** to `C:\Users\<you>\repo\bassblend`. Start the dashboard from that folder
(`subtune.cmd serve`); the app's preview launcher was still pointing at the old session folder.

**New: blend with both front speakers**
- The blend test can now play the left speaker, then the right, then left again with the subs
  (about 40 s; "Left + right" is the default, "Left only" is still there). The subs get the same
  bass whichever speaker plays, so one "with subs" pass covers both.
- Single-seat and all-seats answers average over both speakers, so the fix doesn't favour one side.
- The graphs show the right speaker too; the all-seats graph has a Left / Right switch.
- A second test file (`bassblend_blend_test_left_right.wav`) for the USB-stick option, made on demand.
- The assistant can choose left or both, and is told to prefer both.
- New offline tests: `tests/test_blend_measure.py` simulates a full mic recording (separate filter,
  delay and level for left, right and subs, plus noise) and checks the analysis recovers all three,
  including their relative timing, and that the subs are unmuted inside the gap. 6 checks, all pass.

**Fixes**
- The "What the tune did" colour key had collapsed into a narrow column (a style-name clash with
  the new seat bars).
- Room-mode labels on graphs no longer print on top of each other.
- Activity log: times ran into the labels; labels are now plain words (miniDSP, measured, setting).
- AI analysis: `*italic*` text now renders instead of showing asterisks.

**Polish**
- The Ask BassBlend button shrinks to an icon on narrower windows so it doesn't cover the page.
- Plain names on the result tiles: Average unevenness, Difference between seats, Biggest swing,
  Turned down for EQ (same names in the tunes comparison).
- "Slot" everywhere instead of a mix of "preset" and "slot"; the tune step names the real slot.
- Receiver screen explains itself when the receiver is in standby.

## Nov 13, 2026 — overnight polish (silent: code, UI and offline tests only)

**Fixes**
- The single-seat blend fix could be applied twice, stacking the delay. It is now tied to the tune
  it was measured with, and marked "Applied" once used.
- Blend fixes now save as a clean new tune (the old tune's slot/time/id are no longer copied in).

**Multi-seat blend**
- Tune building moved into `blend_tune()` (cli.py), so it can be tested without hardware.
- New offline tests: `tests/test_blendmulti.py`, 11 checks using simulated seats (all-pass filter
  maths, the miniDSP coefficient format, optimiser behaviour, MLP weighting, seat storage, tune
  building and refusals). All pass.
- The AI assistant now knows about seats: how to measure them, what "miniDSP fix" vs "receiver
  change" means, and that applying uses the all-seats answer. The overview it reads includes the
  all-seats result.
- Wizard step 3 shows "N of 3 seats measured" and counts as done once seats are measured with the
  playing tune.

**Polish**
- Filters view shows blend all-pass filters ("phase only", with a short explanation) and the slot
  that's actually playing instead of a fixed "preset 4". Numbers no longer wrap mid-value.
- The blend card's network note is calmer now that the firewall is sorted.
- With no seats measured, the stray "Mic at MLP next" button is gone (Run blend test already starts there).

Checked in light, dark and phone layouts with no console errors. Nothing played, nothing was written
to the miniDSP, and the receiver wasn't changed.

## Nov 12, 2026
- Multi-seat blend: each blend test is saved as a seat; one setting (delay, polarity, optional
  all-pass) is chosen for all seats, MLP weighted most. "All seats" view in the blend card.
- Mic calibration upload in the Setup checklist (validated before use).
- Home redesign: system map, health score, 4-step "Tune my system" wizard, Setup checklist,
  "Ask about this" buttons, assistant docks beside the page on wide screens.
