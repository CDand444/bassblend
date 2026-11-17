# htTamer changelog

## Nov 18, 2026 - cabinet sizes, sub aim, screen frame, soffit-aware treatment

- **Double door** in the openings catalog (Room → shape → Openings, doors and windows): an Add double door button (5 ft, two leaves on the plan and in 3D), the same panel advice as a door, and the phone builder and assistant know it.
- **Ceiling treatment respects soffits**: the ceiling cloud is trimmed to stay clear of every soffit (the plan says which), and the 3D view leaves no tile where one hangs.
- **Sub aim**: each sub has a "Points at" pick and an angle (0 = back wall, 90 = left, 180 = screen, 270 = right; blank = at the main seat). The plan shows an arrow, the 3D sub turns to face it, the card says which wall it points at and how far, and the treatment plan warns when one fires into a wall a few inches away.
- **Cabinet sizes**: subs and speakers take a width, height and depth in inches, from you, from the hardware database (new fields on subs and speakers, which the assistant can fill in), or a labeled typical size. The 3D views draw the real size.
- **Screen frame**: the screen has a frame or bezel width; the plan, the 3D view and the treatment plan use the whole outer size, and front-wall panels stay off the screen and its frame (unless it is acoustically transparent).

## Nov 18, 2026 - a better 3D view, treatment in 3D, risers

- **Treatment in 3D**: the Treatment page has a Plan / 3D switch. Wall panels, ceiling clouds, the rug and corner traps are drawn where the plan puts them, with your couches, speakers and subs.
- **A fuller 3D view** (Room and Treatment): shaded solid objects with ground shadows; speakers as cabinets with a cone facing your seat; ceiling speakers hung from the ceiling; subs as cubes; couches with arms, cushion and back; your view angle is kept; double-click resets it.
- **Risers**: couches sit on risers by themselves (they rise with them in 3D, stay inside the edges, follow when the riser moves), a new couch lands on a riser, a new riser fits under a couch, and the page says when a couch hangs off its riser. Added Sit on a riser and Fit to couch.

## Nov 17, 2026 - house, apartment or condo

- **Where you live** on the Room page: home type, floor, who shares your floor, ceiling or walls, wood or concrete. Shared buildings get
  a gentler bass-lift step on Home, a quiet-hours suggestion, test-timing and sub-placement tips, rental-friendly treatment notes and a
  structure note on room modes. The assistant can record it too.
- **Quiet hours**: night mode can switch itself on at a set time (Automation); turning it off yourself overnight is respected.

## Nov 17, 2026 - 1080p review, folded AI suggestions

- **AI suggestions are folded and closed by default** (suggested setup, per-sub suggestions, room analysis, the phone builder's assumptions
  and questions); the room analysis says when it is older than the current tune. The AI settings sit in a fold too.
- **Layout at 1080p**: Subs shows two wide cards per row (the page is a third shorter); the automation inputs are a grid instead of one
  long list; the treatment page folds Before and after, Your constraints and What you have installed and has a jump bar; the couch
  reflection note appears once, not once per seat; the Home cards that repeat Results start folded.

## Nov 17, 2026 - Windows: HDMI, the miniDSP lock and wording

- **No Pi wording off the Pi**: pages, messages, the assistant and the CLI say "this computer" unless htTamer runs on a Raspberry Pi.
- **PC HDMI on Windows**: receiver tests, including the 7.1 all-speakers check, can play through the PC's own HDMI output (WASAPI), with
  an output chooser, a 7.1 setup hint and a swap for surround and surround back. The silent check tests it.
- **miniDSP lock on Windows**: commands from different processes (a job and the live EQ) now wait for each other, as on Linux.
- **Firewall help** has a Copy button; the release build's smoke test now runs the silent check and fails if the bundle is missing the
  miniDSP tool or the audio library.

## Nov 16, 2026 (night) - a beginner view, one results screen, readiness

Built and tested offline and in a browser against copies of real results; the real-hardware protocol is in `docs/dev/HARDWARE_VALIDATION.md`.

- **Basic / Advanced**: Basic shows Home, Setup, Calibrate, Results and Compare; everything else is behind "Show all pages". New
  systems start in Basic, calibrated ones keep Advanced.
- **Results** (Verify): the response before and after, seat consistency, crossover integration and the listening comparison on one page,
  with what improved, what did not and what is not measured. Expected numbers are labelled as expected until a verify measures them.
- **Is it ready?** (Home): connected, set up, verified (with when) and never tested, and a ready / caution / blocked verdict; a hardware
  check that is old is shown as unknown.
- **Your first calibration**: one button, one mic spot, no room, speaker or furniture details needed first.
- `scripts/validation_snapshot.py` snapshots and compares repeated hardware runs against limits.

## Nov 16, 2026 - room details, backups, receiver setup sheet

Built and tested offline (the offline tests and a headless browser); the receiver setup sheet, a real backup restore and the
new room details are still to be tried on the real system.

- **Room page**: a **Screen** section (TV or projector screen, size and shape, acoustically transparent or not, front speakers
  behind it), **Furniture** (couches with fabric and size, risers), **Soffits** along walls (trimmed to their wall and blended
  into angled walls), a jump bar, and "Pick screen wall". Plan and 3D draw everything; pointing at a soffit, opening or corner
  row lights it up on the plan and in 3D. Room and Subs are now two pages.
- **Treatment and layout**: couches, risers, soffits and the screen add notes (ring-time estimate, couch back at the ears, a
  front-wall soffit, viewing angle, what an AT screen does); front speakers sit close behind an AT screen.
- **Backups** (Tools, Beta): weekly, before an update and on demand; the newest five are kept; restore with a safety copy first;
  never holds keys, PIN or tokens; optional second copy to a USB stick or share.
- **Receiver setup sheet** (after the all-speakers check): level and distance changes per channel in the receiver's words,
  final numbers from the values recorded at measurement time, tonal match and bass extension per channel; printable at `/channels`.
- **Assistant and MCP**: update_room records the screen, furniture and soffits; list_backups, make_backup and restore_backup
  (the last needs your approval). The phone room builder can also propose the screen, couches, risers and soffits.
- **Layout**: pages scale to wide screens; Speaker placement and Room treatment use a plan-and-table layout.

## Nov 14, 2026 (overnight) - pro views, placement, headroom, all speakers, offline helper

Built and tested offline (simulations and the browser); nothing played on the real system.

- **Offline helper**: with no AI provider, the chat answers from htTamer's own data (next steps,
  latest report, sub settings with warnings, receiver processing, playing tune) and a glossary.
- **Settings files** carry system reports, report history, the last fixes and the tuning journal.
- **System report pro views**: phase, group delay, impulse and step response, bass waterfall
  (0-300 ms), and REW export (frequency, SPL, phase per channel).
- **Multi-spot average**: with reports at 2+ spots, an "All spots (average)" view shows the
  response over the listening area, spot-to-spot spread, and marks treble findings seen at one
  spot only as mic-position effects.
- **Speaker placement** (Setup): Dolby-guideline positions for the layout from the room and main
  seat, each within its allowed angle on its own wall, with notes (e.g. your MLP sits near the
  room's first bass null, and front speakers fit at 23-25 degrees rather than 30).
- **Sub headroom** (Measure, not yet run): rising tone bursts at 25/40/63 Hz per sub with automatic
  stops (5-10% distortion, 3 dB compression, mic overload, 105 dB, -12 dBFS).
- **All speakers** (Measure, experimental, not yet run): the receiver's network player is
  stereo-only (it lists 1-2 channel PCM), so a 7.1 WAV is played by the owner from an HDMI source
  or USB stick; every bed speaker and the LFE are checked against the front left for level,
  arrival, polarity and whether it played. Heights need Atmos content and aren't covered.
- **Sub catalog**: SVS PB-2000 Pro (port plugs vs the app's Standard/Sealed mode) and Rythmik F12
  (extension, damping, rumble, low-pass mode), from the makers' pages and guides.
- Tests: `test_helper.py`, `test_layout.py`, `test_headroom.py`, `test_allspk.py`, additions to
  `test_deepcheck.py`, `test_bundle.py` and `test_vendors.py`.

## Nov 14, 2026 - tuning coach, journal and a holistic assistant

- **Tuning coach** (`subtune/coach.py`): ranked next steps from all the data, in the order the
  chain depends on (safety and wiring, sub hardware, sub tune, blend, receiver, Dirac, verify and
  listen); each says why, who does it, whether it plays sound and the tool to use. Shown as a
  "Next steps" card on the main page (no AI needed) and given to the assistant. Never offers a
  blend fix the playing tune already contains; asks for a fresh report when the last one predates
  the current htTamer.
- **Tuning journal** (`subtune/journal.py`): knob changes, tunes applied, receiver level and
  processing changes, Dirac runs, target changes, verifications, reports and fixes with their key
  numbers; on the main page and in the assistant's overview.
- **Assistant rewritten** as a tuning engineer: live system facts instead of a hard-coded
  description, an explicit loop (assess, propose one step, act, measure, compare, keep or undo),
  work ordered across the chain, a concrete next suggestion in every reply, a quiet mode for "no
  sound now", and new tools `get_tuning_plan` and `get_journal`.
- Tests: `test_coach.py` (12).

## Nov 13, 2026 (evening) - vendor-aware subs, AI providers, receiver control and fixes

- **Vendor-aware subs**: Room & subs shows each catalog model's own controls. Hsu VTF-3 MK5 HP
  (from Hsu's manual): ports, EQ1/EQ2, Q 0.3-0.7, crossover In/Out and frequency, phase 0/180,
  volume, power; the five operating modes; a danger warning for both ports open with EQ1. SVS
  SB-1000: volume, low-pass/LFE, phase. Stacked-crossover warnings. Ported modes get no EQ boost
  below a conservative limit. The assistant sees settings, modes and the maker's guidance.
- **AI providers**: Anthropic (default), OpenAI, Google Gemini or a local OpenAI-compatible
  server (Ollama, LM Studio). Key per provider, models from the provider's live list (a sensible
  one is picked automatically), Test button; assistant tools and analysis work with all of them.
  Provider choice and (optionally) keys travel in the settings file.
- **Receiver control**: centre level; sound processing (bass/treble, Late Night, Cinema Filter,
  Music Optimizer, dialogue enhance, dimmer) plus temperature and input signal, all confirmed
  supported by the TX-RZ50's own capability list. Tests switch the colouring processing off and
  restore it afterwards.
- **Fix what htTamer can** (System report): receiver sub level to the target (max +3 dB up),
  left+right blend test with the blend fix applied when it helps (never slot 1), then a new report
  with before/after. Receiver advice with exact menu numbers (distance, level) and Dirac notes.
- **Report history** with a before/after overlay; Dirac target "Matched to your speakers" (the
  measured in-room treble slope), recommended Dirac settings, Hsu auto-EQ reminder.
- **8 s lead-in** on the test files (the receiver skipped the start of network playback, losing
  the left sweep's deepest bass); the report flags a clipped start.
- Tests: `test_vendors.py`, `test_ai.py` (fake provider server, full tool loop), `test_fixup.py`,
  receiver processing in `test_deepcheck.py`.

## Nov 13, 2026 — system report, automatic receiver volume, header SPL meter, target slot

- **System report** (menu → Measure): a 20 Hz-20 kHz sweep on the left speaker, the right, then
  both, through the receiver in Stereo with the subs on. Plain-language findings with why they
  matter and what to do: tone per range vs the target, peaks and dips classified (room
  resonance, wall cancellation with distance, reflection ripple), left/right level, timing (seat
  centring) and polarity (a speaker wired backwards), RT60 per octave, early reflections,
  distortion, noise and hum, measurement reliability, bass extension. Chart, detail tables,
  glossary, **Print / Save as PDF**. The assistant can read and run it. Front L/R and subs only.
- **Automatic receiver volume** for the system report and the blend test: pink noise, then the
  volume steps (at most 3 at a time) to the test level at the mic (75 dB C default), never above
  the max you set (default: your volume + 12, never above 70), turning down and stopping if the
  mic overloads; your volume, input and mode are put back afterwards.
- **Receiver restore fix**: the before-test snapshot now retries and refuses to start a test
  without knowing the volume and input (a slow reply had left the receiver at the test volume);
  a receiver that was in standby gets its volume back before going back to standby.
- **SPL meter in the header**: always on while the dashboard is open, fed by the test itself
  while sweeps or tones play ("TEST"); the mic is reserved for the whole job, and measurements
  wait up to 5 s for it (on the Pi only one program can hold the mic).
- **Tune into slot 2, 3 or 4**: auto-tune's whole run (reset, sweeps, apply, verify) uses the
  chosen slot; slot 1 can't be picked.
- Tests: `test_deepcheck.py` (12, synthetic room with planted problems), `test_slot.py`,
  `test_spl_tap.py`.

## Nov 13, 2026 — settings file and over-the-air updates

- **Settings file**: menu → Settings file saves room, speaker layout, subs, receiver, mic
  calibration and (by default) tunes, slot contents, the current result and measurements to one
  `.json`. PIN (as its hash) and API key only when ticked. Import it from the same page, the
  first-boot setup page, or `subtune import-config`. Machine-specific settings (USB path, audio
  device names) are never carried, so a Windows file works on the Pi. A file can't give htTamer
  slot 1, and only known data files are written.
- **First boot**: `bassblend-config.json` on a fresh card's boot drive is imported automatically
  and removed from the boot drive. `BASSBLEND_SETTINGS=` bakes one into an image build.
- **Over-the-air updates**: `deploy/push-update.sh [--watch]` sends the code over SSH;
  `bassblend-update` on the Pi checks it compiles, installs, restarts only for Python changes and
  rolls back if the new version doesn't start.
- The version shows in the dashboard; image builds write it to `BASSBLEND.txt` (was "dev").
- The saved API key file is owner-only on Linux. 6 checks in `tests/test_bundle.py`.
- **Pi fix: miniDSP "not detected"**. Without a cached address, minidsp-rs also searched the
  network for ~10 s on every call, so the dashboard's status check kept the USB device busy and
  other commands (slot switches) failed with "No devices found". Calls now look only over USB
  (`--usb 2752:0011`, ~0.1 s), take turns (thread + file lock shared with job subprocesses), and
  retry briefly when the device is busy.

## Nov 13, 2026 — first-boot setup in the browser (for a ready-made SD card)

- A fresh htTamer in network mode (no PIN yet) shows a **setup guide** instead of the dashboard:
  1. choose a PIN, 2. add the mic calibration file, 3. find the receiver (automatic search, or by
  hand), 4. add the AI key (optional). Steps can be skipped or changed later; "Finish later and
  open htTamer" lands on the Setup checklist.
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
  use Dirac Live and its Bass Control. htTamer only uses this to guide you; it changes nothing in
  the receiver. Includes a "Receiver settings to check once" list built from the layout.
- **Dirac Live step in the wizard** (shown when you use Dirac): what to check first, a download of
  htTamer's target as a Dirac target-curve file (Flat / Gentle / Warm treble, with a small graph),
  seven plain steps for running Dirac, and an "I've run Dirac Live" button.
- htTamer remembers which sub tune Dirac was run with. A blend fix keeps it valid (it only shifts
  timing); a new sub tune asks you to run Dirac again. Marking Dirac as run clears older blend
  measurements, since the speakers then sound different.
- Setup checklist has a "Speakers and Dirac Live" line; the system map shows the layout and Dirac state.
- The assistant knows the layout, the Dirac order of steps, and that it can't operate Dirac itself.
- Fixes: the system map could show "Not set by htTamer" until the slot names loaded.
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
- The Ask htTamer button shrinks to an icon on narrower windows so it doesn't cover the page.
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
