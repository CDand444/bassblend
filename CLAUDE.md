# htTamer: guide for Claude

htTamer auto-tunes home-theater subwoofers: UMIK-1 mic → measurements → gain/delay/polarity/PEQ
written into a **miniDSP 2x4HD** (via `minidsp-rs`), plus receiver-side tests (Onkyo eISCP), a live
EQ with analyzer, and an in-app AI assistant. It runs on a **Raspberry Pi 4** (production) and
Windows (dev). Web UI on port 8765. Read this before exploring; it should save re-discovery.

## Names (don't "fix" these)
- User-facing name: **htTamer**. Infrastructure keeps the old names on purpose: Python package
  `subtune`, paths/host/service `bassblend`, settings format id `bassblend-config`.

## Layout
- `subtune/` (all Python, stdlib HTTP server, numpy/scipy, sounddevice)
  - `server.py`: web server, all `/api/*` routes, `Runner` (one job at a time, each job is a
    `python -m subtune <cmd>` subprocess), `LiveWriter` (live EQ writes), assistant executors
    (`build_executors`)
  - `cli.py`: every job command (`apply`, `avrblend`, `deepcheck`, `fixup`, `liveeq`, `smoke`, …).
    SIGTERM (Stop) raises SystemExit so each job's `finally` restores the receiver
  - `assistant.py`: assistant system prompt, tool schemas (`_t`), approval descriptions;
    `ai.py`: providers (Anthropic, OpenAI, Gemini, local OpenAI-compatible)
  - DSP: `dsp.py` (minidsp-rs wrapper + device lock), `biquad.py` (RBJ, DSP_FS = 48 kHz;
    miniDSP form `[b0,b1,b2,-a1,-a2]`), `optimize.py` (multi-sub fit), `library.py` (tunes, slots)
  - Measuring: `measure.py`, `audio.py` (sweeps, cal), `splmeter.py`, `autolevel.py` (guarded volume)
  - Receiver: `avr.py` (eISCP, DLNA, snapshot/restore), `hdmi.py` (Pi HDMI playback `Source`),
    `avrmeasure.py` + `blendmulti.py` (blend), `deepcheck.py` (system report), `fixup.py`,
    `fixlog.py` (fix ledger vs baseline), `allspk.py`
  - `liveeq.py`: live EQ layer (free top PEQ bands), analyzer (`run_rta`), `autofit`
  - `smoke.py`: silent hardware check. `state.py`: state.json (locked read-modify-write), events
  - Data/model: `config.py` (paths, settings), `room.py`, `equip.py`, `dirac.py`, `layout.py`,
    `vendors.py`, `coach.py`, `journal.py`, `helper.py`, `bundle.py`, `auth.py`
- `subtune/web/`: `index.html` (markup + CSS), `js/*.js` (page script in 8 parts, loaded in order as
  classic scripts sharing globals: core, tune, room-ai, receiver, measure, setup-home, liveeq, nav),
  `manual.html` (user manual, also `/manual`), `setup.html`, `logo.svg`
- `tests/test_*.py`: offline, no hardware, no sound; each file runs on its own
- `deploy/`: `push-update.sh` (OTA to the Pi), `linux/` (install, updater), `pi-gen/` (SD image)

## Commands
- Tests (Windows): `& "$env:LOCALAPPDATA\subtune-venv\Scripts\python.exe" tests\test_X.py`.
  Always run `tests/test_compile.py` before deploying: the Pi refuses code that doesn't import.
- Deploy to the Pi: `bash deploy/push-update.sh` (sends tracked + new files, restarts, rolls back
  if it fails). The owner does the real testing on the Pi; local preview isn't needed unless a
  change can only be checked in a browser (e.g. the JS split).
- Pi: `ssh bassblend`. App in `/opt/bassblend` (venv `/opt/bassblend/venv`), data in
  `/var/lib/bassblend` (not readable as the ssh user: use the API, e.g.
  `curl -s http://127.0.0.1:8765/api/state`, local requests need no sign-in). Running a test file
  there: `BASSBLEND_DATA=$(mktemp -d) BASSBLEND_CONFIG=... /opt/bassblend/venv/bin/python3 tests/...`
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
- Applying any tune rewrites all PEQ bands (live EQ switches off).

## Hardware facts
- Receiver's DLNA player is effectively stereo-only; multichannel tests need the Pi's HDMI
  (`vc4hdmi0` → receiver input saved as `avr_pi_input`). HDMI 8ch needs the reordered channel map
  in `hdmi.py`. Heights can't be reached from LPCM.
- Onkyo sub level set over the network is temporary and resets on input change; `restore()` re-sets it.
- miniDSP normal input is `restore_source` (i2s); USB means the subs don't get the receiver's bass.
- Pi runs Python 3.13; Windows dev venv 3.12.

## Keeping things current
- New user-visible feature → update `subtune/web/manual.html` (and the assistant prompt if it can use it).
- New page → card in `index.html`, entry in `MENU` (`js/nav.js`), render function in the right `js/` part.
