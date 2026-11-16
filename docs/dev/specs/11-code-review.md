# Spec 11: whole-repo code review

**Goal:** a systematic review of every module for real defects, safety-rule breaks and security holes, with each finding checked before anything is changed. The review finds and reports; it never edits code.

**When:** after the queued features are done and deployed (the owner's order). Nothing in this spec starts before that.

## Method

1. **Sweep (local model, Qwen3.8 27B, one batch per fresh session).** Each batch reviews a small group of files read-only and writes ONE findings file, `docs/dev/review/<batch-id>.md`. Batches are at most about 900 lines so the whole batch fits in the model's context with room to think; `server.py` is split by line range.
2. **Verify (the manager, Claude).** Every finding of severity high or medium is checked by reading the cited lines before it is believed. The local model invents problems and misreads code; an unverified finding is never acted on. Findings that do not hold are marked `rejected` with a one-line reason; the file is kept as the record.
3. **Fix (the normal task loop).** Confirmed findings become small fix tasks, highest severity first, each with a test that fails before the fix. Fixes are never batched with unrelated changes.
4. **Cross-cutting pass (the manager).** After the sweep, one targeted pass over the rules in CLAUDE.md that span modules: nothing plays sound without the owner's say-so, miniDSP slot 1 is never written, receiver volume only moves through the guarded auto-level and is always restored, no API key is ever shown, every `/api` and `/mcp` route is behind sign-in and the terms gate, every new tool is in `guard.SOUND`/`CHANGES` when it can make sound or change things.

## What the reviewer looks for (the lenses, in this order)

1. **Safety rules** above (sound, slot 1, volume, keys, sign-in, guard lists).
2. **Correctness**: wrong math or units (m vs ft, dB vs linear, Hz vs rad), off-by-one, wrong sign, stale data used where measured data is required ("measured, not current"), results not tied to the tune that produced them.
3. **Failure handling**: exceptions swallowed in a way that hides a real problem, missing restore of receiver or miniDSP state in a `finally`, a job that can leave the device in a changed state, no timeout on network or device calls.
4. **Concurrency**: shared state without a lock, read-modify-write on files without the locked helper, the one-job-at-a-time rule.
5. **Input handling**: paths from requests, numbers without limits, anything reaching a shell, file or network call.
6. **Privacy**: personal data in logs, bundles, the assistant prompt or the repo.
7. **Dead code and drift**: unused functions, comments that no longer match the code (reported, low priority).

Not in scope: style, naming, spelling (done), performance unless it is a bug, and rewriting working code.

## Finding format (one block per finding, in the batch file)

`### F<n>: <short title>` then lines: `severity: high|medium|low`, `where: path:line`, `what: ...`, `why it matters: ...`, `evidence: the exact lines quoted (max 6)`, `suggested fix: ...`, `confidence: high|medium|low`. The header of the file lists the files reviewed with their line counts and ends with "Not reviewed:" for anything skipped. A batch with no findings says so and says what it checked.

## Batches

| id | files |
|---|---|
| r01-safety | guard, limiter, gaincheck, autolevel, legal, auth, helper |
| r02-ai | assistant, ai |
| r03-mcp-bundle | mcp, bundle |
| r04-receivers | avr, receivers |
| r05-hw | hdmi, rxinfo, hwdb, dsp, smoke |
| r06-measure | audio, measure, splmeter, checkup, headroom |
| r07-eq-core | optimize, biquad, analysis |
| r08-live | liveeq, blendmulti |
| r09-fixes | avrmeasure, allspk, fixup, fixlog, abtest |
| r10-reports | deepcheck, library, dirac, limits |
| r11-room | room, shape, orient, equip |
| r12-place-treat | layout, treatment |
| r13-room-extras | builder, coach, subouts, vendors, qr, furniture |
| r14-plumbing | state, config, journal, report, automation, update, feedback, ha |
| r15-cli | cli |
| r16-server-a | server.py lines 1-900 |
| r17-server-b | server.py lines 900-1800 |
| r18-server-c | server.py lines 1800-end (the `/api` routes: check sign-in and terms gate on each) |
| r19-js-core | web/js: core, nav, tune, receiver |
| r20-js-room | web/js: room-ai, room3d, furniture |
| r21-js-rest | web/js: measure, setup-home, liveeq; web: build.html, setup.html |
| r22-deploy | deploy/push-update.sh, deploy/linux/*, deploy/windows/*, .github/workflows/* |

## Running a batch (manager)

`agent.ps1 start <id> -Brief <brief>` where the brief names the files and lenses, tells the agent to Read each file in chunks of at most 120 lines, to write only `docs/dev/review/<id>.md`, and to quote evidence. After the sweep, a one-page `docs/dev/review/SUMMARY.md` lists every finding with status (confirmed / rejected / fixed) and the fix commit. Estimated 2 to 3 hours of model time for the sweep, one to two hours of verification.

## Done when

All 22 batch files exist; every high and medium finding is confirmed or rejected with a reason; every confirmed high finding is fixed with a test; SUMMARY.md is current; the full suite, pyflakes and the browser check pass. Review files stay in the repo under docs/dev (not shipped: `docs/dev/** export-ignore`).
