# Spec 01: split `server.py` into small modules

**Goal:** `subtune/server.py` (about 2,600 lines) ends under 1,200 lines. No behavior change: same endpoints, same replies, same checks in the same order.

**Why:** it holds every endpoint and the assistant's tool executors; it is too big to read, review or safely edit. See `docs/dev/ROADMAP.md`, item 1.

## Rules for this refactor

- **Behavior must not change.** No renamed endpoints, no new ones, none removed, no changed replies.
- **Order matters for safety.** Keep these exactly as they are in `server.py`:
  - routes answered *before* the sign-in gate: `/build.webmanifest`, `/apple-touch-icon.png`, `/build?pair=...`, `/api/ha/*`, `/mcp`;
  - the use-at-your-own-risk gate in `do_POST` (`if path not in legal.OPEN_PATHS and not legal.accepted():`). `tests/test_legal.py` checks that this line is in `server.py`: leave it there. Every action route must come after it.
- One area per step. After each step everything passes and the app starts.
- Helper methods stay on `Handler` (`_send`, `_gate`, `_authed`, `_redirect`, `_setup_needed`); new modules call them through the handler they are given.

## Step 0: a route snapshot test (do this first)

Create `tests/test_routes.py` and `tests/routes.txt`. The test scans every `.py` file under `subtune/` for route literals (`path == "/api/..."`, `u.path == "..."`, `path in (...)`, `path.startswith("/api/ha/")`), builds a sorted list, and compares it with `tests/routes.txt` (check the generated list in). It must pass before and after every later step: the list may not change.

## Step 1: move the assistant's tool executors

`build_executors` and its inner functions (about 400 lines) move to `subtune/executors.py`. `server.py` keeps a one-line `build_executors = executors.build_executors` (or imports it) so `assistant()` and `mcp_server()` still work. Inside `executors.py`, reach server state with `from . import server as srv` *inside the function* (avoids a circular import): `srv.RUN`, `srv.avr_status`, `srv._live`, and so on. Tests that must stay green: `test_coach`, `test_guard`, `test_mcp`, `test_automation`, `test_limits`.

## Steps 2 to N: route groups

Create a package `subtune/api/`. Each area gets one file exposing two functions:

```python
def get(h, path, q) -> bool:      # True when this module answered the request
def post(h, path, body) -> bool:
```

`do_GET` and `do_POST` in `server.py` keep the gate checks, then loop over a list of these modules (in a fixed order) and stop at the first that returns True; the old fall-through (404 / "not found") stays at the end. Move one group per step, smallest and newest first:

1. updates (`/api/update`), feedback (`/api/feedback`), terms
2. automation, blind A/B, Home Assistant (`/api/automation`, `/api/ab`, `/api/homeassistant`)
3. MCP settings (`/api/mcp`), phone builder (`/api/build/*`)
4. hardware database, AI provider settings (`/api/ai`), chat (`/api/chat*`)
5. Live EQ, receiver (`/api/avr*`), room and equipment
6. tunes, jobs (`/api/run`, `/api/verify`, ...), state, events, static files

Module-level helpers used by only one group move with it; shared ones go in `subtune/api/common.py`.

## Definition of done (per step)

- `tests/test_routes.py` passes with an unchanged `routes.txt`.
- `tests/test_compile.py`, `pyflakes`, and every touched test file pass. The manager runs the whole suite and `tests/browser_check.py`.
- `server.py` is smaller than before the step, and no new file is over 400 lines.
- Report: lines before/after for `server.py`, the files created, the tests run.

## Out of scope

Changing any endpoint's behavior or name, switching web frameworks, async code, touching the page scripts.
