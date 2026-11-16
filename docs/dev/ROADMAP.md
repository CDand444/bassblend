# htTamer roadmap and design decisions

Written at v0.9.10. Read `CLAUDE.md` first (layout, rules), then `docs/dev/LOCAL_MODELS.md` (how to work), then the spec for your task in `docs/dev/specs/`.

**Roles.** *Owner*: owns the room and hardware, makes decisions, runs anything that plays sound. *Local models* (Claude Code on a local coder model): write all the code, tests and docs. *Manager* (a Claude session): plans, writes these documents, runs the full checks, commits, pushes, deploys and releases. Local models don't commit, push, deploy or tag.

## Where things stand

- **Proven on real hardware** (Raspberry Pi 4, miniDSP 2x4HD, an Onkyo receiver): auto-tune, measure, apply, verify, check-up, level match, headroom and limiters, the blend test and fix log, the system report, receiver control, updates (Windows and the Pi), the assistant on Claude.
- **Tested offline only, so labeled or treated as Beta:** Live EQ, the all-speakers check, room treatment, the hardware database, MCP, the Denon/Marantz and JBL drivers, room shapes and the phone room builder, night mode, automatic slot, the watchdog, the blind A/B test, Home Assistant, receiver auto-off, "what limits this tune", and the assistant on a local model.
- **GitHub checks** run on every push (`.github/workflows/ci.yml`): pyflakes, all offline tests on Linux (Python 3.13) and Windows (3.12), and a browser check of every page. A release builds only if they pass.

## What to improve, in order

### A. Make the code workable for small-context models
The local coder runs with a 128k-token window, minus about 13k for Claude Code's own prompt. That is enough to read a medium file whole, but `server.py` alone is roughly 35k tokens, and local models get slower, less accurate and more forgetful as the window fills. Small files keep every task fast and precise.

| # | Item | Why | Spec |
|---|------|-----|------|
| 1 | Split `server.py` (2,580 lines) into small route modules | It holds every endpoint and the assistant's tool executors; nothing else is this big a problem | `01-split-server.md` |
| 2 | Test suite health | `test_mcp.py` drops a connection now and then on Windows, and the full suite takes about 10 minutes | `05-test-health.md` |
| 3 | Type hints and mypy on the safety modules | Wrong-argument mistakes only show when code runs; small models make them more | `04-typing.md` |

Other files over 450 lines: `index.html` (1,346: markup and CSS), `treatment.py`, `room-ai.js`, `deepcheck.py`, `assistant.py`, `cli.py`, `measure.js`. Split them only when a task touches them (leave each one smaller than you found it).

### B. Features
| # | Item | Spec |
|---|------|------|
| 4 | Automatic backups and one-click restore (a bad SD card or update must never cost the owner their tunes) | `02-backups.md` |
| 5 | Room drawing by dragging walls and corners, with validation and undo | `03-room-drag.md` |
| 5b | Rotate the room's orientation (choose the screen wall, quarter turns, mirror) with everything in it turning too | `06-room-orientation.md` |

### C. Needs the owner at the hardware
The manager schedules these; local models only fix what they uncover.
6. **Five open findings from the first full system run:** one sub output was never heard in the headroom test; the LFE check measured only +2 dB over redirected bass (expect +10); the surround backs arrive 6–10 ms early and 4–6 dB loud (wiring or channel assignment); the gain check says "would clip" until "Loudest you listen" is set; a limiter was proposed at -33.5 dBFS (auto-apply is blocked).
7. **The room's physical limits:** a 7 dB dip at 55 Hz (a length mode) and 1.4–1.6 s ringing at 20–31 Hz. The fix is placement: move one sub or the seat, then verify and check-up at the main seat.
8. **First real runs of the newest features:** night mode, automatic slot, watchdog, blind A/B, Home Assistant, receiver auto-off, the phone builder on a real phone, MCP with a real client, the Denon and JBL drivers (needs someone with those receivers).

### D. Product polish for 1.0
9. Getting-started guide and screenshots in the README; a simple project page with the downloads.
10. **Dirac slot selection.** The receiver has three Dirac Live slots but no documented network command. Plan: listen to what the receiver announces on the network while the owner changes slot with the remote, then confirm the command by sending it. Needs the owner and the receiver.
11. HTTPS on the Pi (so the phone builder can use the live camera).
12. Long-term trends: how the room measures over months.

### E. Scope: what an all-around tuner still needs (proposed, awaiting the owner's decision)
htTamer is strong on subs and the miniDSP. To be an all-around home theater audio tuner it should grow in these directions, in this order. Nothing here is approved until the owner says so.
1. **Every channel, not just the subs** (chosen first by the owner; spec `07-every-channel-report.md`). Measure and report each speaker (center, surrounds, heights, not just front left/right) with one "what to set in your receiver" sheet: crossover, level trim, distance and size per channel, in the receiver's own menu wording. Builds on the all-speakers check (which is still experimental).
2. **A crossover and bass-management recommender.** Pick the crossover frequency and slope from the measured extension of the main speakers and the subs' bandwidth, and check the blend at that frequency.
3. **Work without a miniDSP.** A measure-and-advise mode for receiver-only systems (the audience is much larger), and support for more of the miniDSP family that `minidsp-rs` already drives (Flex, HTx and others), not only the 2x4HD.
4. **More receivers.** Yamaha first (a documented HTTP interface), then Anthem, NAD and Arcam; keep the manual playback path polished for everything else. Only Onkyo is verified on real hardware today.
5. **Room-correction coordination.** Target-curve exports for Dirac, Audyssey, YPAO and MCACC, and the Dirac slot selection (spec idea 10 above).
6. **Low-volume loudness.** A profile that adds bass at low listening levels (the opposite of night mode), switched by volume or listening mode.

**Simplify and remove (also proposed):**
- Fold the separate "AI analysis" page into the assistant: one AI place, not two.
- The setup checklist, the "Tune my system" wizard, the coach and the check-up overlap: make one guided flow.
- 29 menu pages is too many for a newcomer: a Basic view (guided flow plus the essentials) and an Advanced view; put the Beta features (Live EQ, treatment planner, MCP, Home Assistant, hardware database, phone builder) behind a "Labs" switch.
- Group MCP, Home Assistant, the hardware database and the local AI settings under one "Integrations" page.
- Don't build our own full-range room correction for the main speakers: Dirac and its peers own that; stay in the lane of subs, system setup and verification.

### Housekeeping
- `drag-and-drop-implementation.md` at the repo root is a stray notes file: delete it or move it to `docs/dev/`.
- Owner infrastructure (not code): reserve a fixed address for the AI desktop in the router; keep its firewall on; create the CPU-only copy of the vision model for photos.

## Design decisions (keep these unless the owner changes them)

- **D1. Python, standard-library web server, numpy/scipy.** No rewrite. The maths libraries are the reason; speed doesn't matter because the miniDSP does the audio.
- **D2. Safety invariants, never weakened:** nothing plays sound unless the owner started it or approved it; miniDSP slot 1 is never written by tuning, tests or the AI; the receiver volume is only raised by the guarded auto-level (ceiling 70) and always restored; no firewall or security changes; keys, tokens and the PIN never go to an AI or into logs; no personal information in the repo (`tests/test_no_personal_info.py` enforces it).
- **D3. Measured, not predicted.** Advice from a measurement uses the conditions stored with it; the assessment prefers the verify measurement over the prediction.
- **D4. The AI acts only through guarded tools.** Every assistant and MCP tool is wrapped by `guard.py` (read-only mode, argument caps, a sound budget, hardware-database limits). A new tool that plays sound or changes anything must be listed in `guard.SOUND`/`CHANGES`; `tests/test_guard.py` fails otherwise. The assistant needs the owner's approval for anything that plays sound or changes something.
- **D5. Local models first for the assistant.** The assistant runs on a local coder model (`qwen3-coder`), photos on a vision model; Claude stays one setting away. `ai.py` understands the coder model's text-format tool calls. Never use the plain `qwen3-vl` tags (they are "thinking" models and answer empty).
- **D6. Size budget for new code:** modules under 400 lines, functions under 60. A task that makes a file bigger than 600 lines first splits it.
- **D7. No new dependencies** without the owner's approval (the Windows installer and the Pi image must keep building).
- **D8. The page is 8 classic scripts sharing one global scope.** A top-level name declared in two scripts makes the browser drop the second file. New names get a short prefix for their area; `tests/test_js_globals.py` catches clashes.
- **D9. Beta policy.** A feature not yet proven on real hardware carries a Beta label in the menu, the page title and the manual.
- **D10. Every user-visible change updates `subtune/web/manual.html`;** a new page also gets a card in `index.html` and an entry in `MENU` (`js/nav.js`).
- **D11. Releases:** the manager tags `vX.Y.Z` on a clean, tested commit; GitHub builds the Windows installer after the checks pass; the manager builds the Pi image and attaches it; devices update from Tools → Updates.

## Suggested order

1 and 2 first, in parallel (the rest gets easier); then 4; 5 whenever; 3 alongside; section C whenever the owner has time at the room.
