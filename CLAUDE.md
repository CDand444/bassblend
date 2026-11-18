# htTamer: guide for Claude

htTamer auto-tunes home-theater subwoofers: UMIK-1 mic → measurements → gain/delay/polarity/PEQ
written into a **miniDSP 2x4HD** (via `minidsp-rs`), plus receiver-side tests (Onkyo eISCP), a live
EQ with analyzer, and an in-app AI assistant. It runs on a **Raspberry Pi 4** (production) and
Windows (dev). Web UI on port 8765. Read this before exploring; it should save re-discovery.

## Names (don't "fix" these)
- The name is **htTamer** everywhere: paths, service and account `httamer`, variables `HTTAMER_*`, settings format id
  `httamer-config`, GitHub repo `htTamer`. Only the Python package keeps its name, `subtune`.
- The project's earlier name survives only as migration code, on purpose (config.py `_env`, bundle.py `OLD_FORMAT`,
  update.py `OLD_PI_UPDATER`, `deploy/linux/bassblend-update`, the move in `deploy/linux/httamer-update`,
  push-update.sh, install.sh's refusal). Don't add it anywhere else, and don't remove those until old installs are gone.

## Layout
- `subtune/` (all Python, stdlib HTTP server, numpy/scipy, sounddevice)
  - `server.py`: web server, all `/api/*` routes, `Runner` (one job at a time, each job is a
    `python -m subtune <cmd>` subprocess), `LiveWriter` (live EQ writes), assistant executors
    (`build_executors`)
  - `cli.py`: every job command (`apply`, `avrblend`, `deepcheck`, `fixup`, `liveeq`, `smoke`, …).
    SIGTERM (Stop) raises SystemExit so each job's `finally` restores the receiver
  - `mcp.py`: MCP server exposing the assistant's tools (`/mcp` on the dashboard; `subtune mcp` is a stdio
    bridge to it that asks the owner via elicitation). Settings `mcp_enabled`, `mcp_actions` (0 off, 1 ask, 2 client).
    Every /mcp request needs a credential, local ones too: MCP token (hash in config `mcp.json`), local key
    (`mcp-local.key`, used by `subtune mcp` as the same user) or a session cookie
  - `assistant.py`: assistant system prompt, tool schemas (`_t`), approval descriptions;
    `ai.py`: providers (Anthropic, OpenAI, Gemini, local OpenAI-compatible)
  - DSP: `dsp.py` (minidsp-rs wrapper + device lock), `biquad.py` (RBJ, DSP_FS = 48 kHz;
    miniDSP form `[b0,b1,b2,-a1,-a2]`), `optimize.py` (multi-sub fit), `library.py` (tunes, slots)
  - Measuring: `measure.py`, `audio.py` (sweeps, cal), `splmeter.py`, `autolevel.py` (guarded volume)
  - Receiver: `avr.py` (eISCP, DLNA, snapshot/restore), `hdmi.py` (Pi HDMI playback `Source`),
    `avrmeasure.py` + `blendmulti.py` (blend), `deepcheck.py` (system report), `fixup.py`,
    `fixlog.py` (fix ledger vs baseline), `allspk.py`
  - `liveeq.py`: live EQ layer (free top PEQ bands), analyzer (`run_rta`), `autofit`
  - Room shape: `shape.py` (outline polygon, openings on walls, sloped/vaulted ceiling; reflections off real
    walls, corners, main box). No outline = the plain L×W rectangle, so old rooms are unchanged. Room modes for
    irregular rooms are an estimate from the main box (labeled so).
  - `builder.py` + `web/build.html`: phone room builder. The dashboard shows a one-time QR (`qr.py`, own encoder)
    that signs a phone in (`/build?pair=`), photos + sizes + notes -> `ai.vision` -> a checked plan the owner saves.
    Needs an AI key; counts against `assistant.spend_ai_call` (the daily budget). Only in network mode (the Pi).
  - `rxinfo.py`: what the receiver reports about itself (SPI speaker setup, IFA/IFV signal, NRI/FWV, TPD),
    decoded and cross-checked. The RZ50 can't report distances, per-speaker levels or crossovers over
    eISCP (SPD/TCL get no reply; port 80 web setup needs a password) — the owner copies them onto the
    Speakers page (`rx_distance_m`, `rx_level_db`).
  - `receivers.py`: Denon/Marantz (telnet 23) and JBL Synthesis SDP/SDR (Harman binary protocol, port 50000;
    also reads speaker types/distances/levels) drivers with the Onkyo driver's method names; `avr.receiver()` picks the driver (make, or a hwdb receiver's `protocol`);
    `avr.hdmi_inputs()` per make. Only Onkyo is hardware-tested.
  - `hwdb.py`: hardware database (receivers/subs/speakers) the owner or, with setting `ai_hwdb`, the
    assistant grows (`hw_lookup`/`hw_save`, plus Claude web_search); used for driver choice and `protect_hz`.
  - `workshop.py` + `js/workshop.js`: the Sub workshop (Tune > Sub workshop): guided active tuning of a catalog sub's own controls (Hsu: ports, EQ, Q) and a sub crawl, each a
    list of measured trials (`Rig.probe`, `subtune probe`, started by the owner's Measure press) with score, plain feedback, retests, a final verification.
  - `livecheck.py`: the live music check (two-channel): the owner's WAV (stored in `MEDIA` as `httamer_live_music.wav`) is the reference, the UMIK the measurement; `analyze` finds the delay, corrects clock drift, and gives H1 response, phase and coherence. Job `subtune livecheck` (`Runner.start_livecheck`, `POST /api/livecheck`); plays sound only when the owner presses Start.
  - `decay.py` + `js/analysis.js`: Verify → Bass analysis, from stored complex measurements only (no sound): waterfall and band ring times, sub/speaker blend phase per seat (as measured and with the blend test's fix), and take-to-take repeatability (`repeat_db`, recorded per spot by `measure_position`). `GET /api/analysis`.
  - `risercut.py`: cuts a riser to the room outline, door-swing arcs, subs, floor speakers and furniture in the way (a contour, or boxes when something stands inside it); `js/roomedit.js` is the top-down Room editor (pop-out, drag and drop, stage 1; 3D editing is next).
  - `modeler.py`: Room-card furniture proposals (stepped risers with couches) from measurements or, via one AI request, from words; `/api/modeler`, nothing saved. Room `floor`/`rug` feed `furniture.floor_coef`.
  - `fixtures.py`: lights, a ceiling projector (and its beam), fans, vents, sprinkler heads, wall lights, plus on-wall/in-wall/in-ceiling speakers: what
    they block (`keepouts`) so the treatment plan works around them, and plain guidance; the Room page Fixtures block is `js/fixtures.js`.
  - `dwelling.py`: house/apartment/condo awareness (neighbor level, gentler target offer, tips; the Room page block, coach steps, quiet hours
    in `automation.py` via `night_on_at`). `dims.py`: sub aim and cabinet sizes (owner entry > hardware database > typical), `aim_hit`.
    `view3d.js`: what goes into the 3D view (speakers, subs, treatment solids that never pass through each other); `treatpick.js`: the
    Treatment page picker (items and value tiers on/off, cost, buy list; kept in localStorage, never changes the plan).
  - `dropbox.py`: optional Dropbox copy of every backup (owner's own scoped app, PKCE sign-in, refresh token in the config folder like an AI key); `_open` is the only network call, tests replace it.
  - `netname.py`: Tools > Network name (`/api/network`): name and port. Pi: `hostname.request` / `port.request` in
    `<data>/update`, applied by the root `httamer-ota` (same path unit as updates; a port change rewrites the service's
    `--port` and restarts it). Windows: network mode, name and port in `DATA/network.json` (the installer's Network page
    writes it too; the launcher reads the port), the name answered by htTamer's own mDNS responder.
  - `backup.py`: automatic backups (weekly, before an update, on demand) and restore; never holds keys/tokens/PIN
    (`secrets_check`). Card Tools -> Backups, `/api/backups`.
  - `channels.py`: the every-channel report and receiver setup sheet from the newest all-speakers check (pure; `/api/channels`,
    `/channels`); a result stores `rx_at_measure` (measured, not current).
  - `results.py` (Verify > Results: before/after, what improved and what did not, from stored results only), `readiness.py` (Home > Is it
    ready?: connected/set up/verified/untested + verdict, from the stored silent-check result), `js/results.js`, `js/readiness.js`,
    `js/quickstart.js` (first calibration in one button). Basic/Advanced lives in `js/nav.js` (`uiMode`, `BASIC_KEYS`; `.adv-only` hides things in Basic).
    Hardware validation protocol: `docs/dev/HARDWARE_VALIDATION.md` + `scripts/validation_snapshot.py`.
  - `screen.py`: the TV or projector screen on the front wall (size, AT or not, speakers behind it); drawn on the plan and in 3D,
    adds viewing-angle and AT notes to the treatment plan. `furniture.py`, `soffit.py`: couches/risers and soffits on the Room page.
  - `limiter.py`, `gaincheck.py`, `report.py` (/report), drift in `measure.py`, LFE check in `allspk.py`.
  - `smoke.py`: silent hardware check. `state.py`: state.json (locked read-modify-write), events
  - Data/model: `config.py` (paths, settings), `room.py`, `equip.py`, `dirac.py`, `layout.py`,
    `vendors.py`, `coach.py`, `journal.py`, `helper.py`, `bundle.py`, `auth.py`
- `subtune/web/`: `index.html` (markup + CSS), `js/*.js` (page script in 25 parts, loaded in order as
  classic scripts sharing globals: core, tune, room-ai, furniture, fixtures, view3d, soffit, enclosure, screen, dwelling, backup, receiver, measure, treatpick, workshop, soundrays, sound3d, soundfield, channels, setup-home, liveeq, nav; plus
  `room3d.js`, a standalone 2D/3D room viewer (`window.RoomView`) shared with `build.html`),
  `manual.html` (user manual, also `/manual`), `setup.html`, `build.html` (phone room builder, `/build`), `logo.svg`.
  Shared globals mean a top-level name declared in two parts makes the browser drop the later file entirely
  (a per-file parse check can't see it): `tests/test_js_globals.py` catches that and duplicate ids.
- `tests/test_*.py`: offline, no hardware, no sound; each file runs on its own
- `deploy/`: `push-update.sh` (OTA to the Pi), `linux/` (install, updater), `pi-gen/` (SD image),
  `windows/` (PyInstaller spec + launcher + Inno Setup script; built by `.github/workflows/release.yml` on v* tags)

## Commands
- Tests (Windows): `& "$env:LOCALAPPDATA\subtune-venv\Scripts\python.exe" tests\test_X.py`.
  Always run `tests/test_compile.py` before deploying: the Pi refuses code that doesn't import.
- Checks on GitHub (`.github/workflows/ci.yml`, every push to main and before every release, which only
  builds when they pass): pyflakes, all offline tests on Linux/Python 3.13 and Windows/3.12, and
  `tests/browser_check.py` (every page in headless Chromium with real reloads) and `tests/browser_actions.py` (clicks the
  buttons that touch no hardware and checks the page updates by itself) `tests/browser_analysis.py` (the Bass analysis page with seeded measurements) and `tests/browser_room_editor.py` (the Room page's sub drop-down, flooring, modeler and top-down editor, split out so it stays fast; keep browser tests small and per-feature); locally all need
  `pip install playwright` + `python -m playwright install chromium`). `tests/test_no_personal_info.py`
  enforces the no-personal-info rule.
- Deploy to the Pi: `bash deploy/push-update.sh` (sends tracked + new files, restarts, rolls back
  if it fails). The owner does the real testing on the Pi; local preview isn't needed unless a
  change can only be checked in a browser (e.g. the JS split).
- Pi: `ssh httamer`. App in `/opt/httamer` (venv `/opt/httamer/venv`), data in
  `/var/lib/httamer` (not readable as the ssh user: use the API, e.g.
  `curl -s http://127.0.0.1:8765/api/state`, local requests need no sign-in). Running a test file
  there: `HTTAMER_DATA=$(mktemp -d) HTTAMER_CONFIG=... /opt/httamer/venv/bin/python3 tests/...`
- Silent hardware check: `POST /api/smoke` or `subtune smoke`.

## Rules (the owner's, all still in force)
- **Never play sound unless the owner started the test or approved it.** Silent checks are fine.
- **Never write miniDSP slot 1** (owner's original). htTamer uses slot 3 (`settings.preset = 2`).
- Receiver volume is only raised by the guarded auto-level (ceiling, max 70), always restored.
- Don't change firewall or other security settings; never show API keys; never type passwords/PIN.
- Commit or push only when asked. Remote: private GitHub `origin`, branch `main`.
- **No personal info in the repo**: no real IPs, names, emails, user paths or location; use
  placeholders (`192.168.1.50`, `C:\Users\<you>\`). Commits are authored `htTamer` (repo-local git
  config); end messages with the Co-Authored-By line from the session.
- License: PolyForm Noncommercial 1.0.0 ("the htTamer authors"). Not MIT/OSI.
- Don't spend the owner's API credit testing the assistant; check tool wiring offline.

## Design principles learned the hard way
- **Measured, not current**: any advice computed from a measurement must use the conditions
  stored with it (sub level, tune id, volume), never today's receiver state. (Blend sub level and
  Fix flow both had this bug.)
- Fixes go through `fixlog`; don't stack blend fixes or bounce the sub level.
- Results tied to a tune go stale when the tune changes (`tune_id` checks).
- Assistant: strict tool schemas only where every property is required, at most 20
  (`MAX_STRICT`); new tools need an executor in `server.build_executors`, a `_brief` label, and a
  `DESCRIBE` entry if `approval=True`. `test_coach.py` checks names and limits.
- AI hardening lives in `guard.py`, wrapped around every executor (assistant and MCP alike): read-only
  mode, argument caps, the sound budget, hwdb changes that only make things safer, an activity-log line
  per action. A new tool that plays sound or changes anything must be added to `guard.SOUND`/`CHANGES`
  (and given limits in `guard.check` if its arguments can do harm). The assistant adds its own
  per-message caps, approval expiry, Stop and the daily request budget; `test_guard.py` covers both.
- Applying any tune rewrites all PEQ bands (live EQ switches off).

## Hardware facts
- Receiver's DLNA player is effectively stereo-only; multichannel tests need the Pi's HDMI
  (`vc4hdmi0` → receiver input saved as `avr_pi_input`). HDMI 8ch needs the reordered channel map
  in `hdmi.py`. Heights can't be reached from LPCM.
- Onkyo sub level set over the network is temporary and resets on input change; `restore()` re-sets it.
- miniDSP normal input is `restore_source` (i2s); USB means the subs don't get the receiver's bass.
- Pi runs Python 3.13; Windows dev venv 3.12.

## Planning documents (read these before starting a task)
- `docs/dev/ROADMAP.md`: where things stand, what to improve in what order, and the design decisions (D1-D11).
- `docs/dev/LOCAL_MODELS.md`: the working agreement for local coding models (hard rules, how to check your
  work, how to report). Local models write the code; they don't commit, push, deploy or tag.
- `docs/dev/specs/NN-*.md`: one small spec per task. Take one at a time, in order; start a fresh session per step.

## Keeping things current
- New user-visible feature → update `subtune/web/manual.html` (and the assistant prompt if it can use it).
- New page → card in `index.html`, entry in `MENU` (`js/nav.js`), render function in the right `js/` part.
