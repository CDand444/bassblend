# Working agreement for local coding models

You write the code. The manager (a separate Claude session) checks it, commits, pushes, deploys and releases. Read `CLAUDE.md` and your task's spec in `docs/dev/specs/` before touching anything.

## Hard rules (never break these)

1. **Never play sound, and never talk to the real hardware or the Pi.** Tests are offline: no sound, no network, no miniDSP, no receiver. Don't call the Pi's API or run `deploy/push-update.sh`.
2. **Never write miniDSP slot 1.** Never raise the receiver volume.
3. **No personal information in the repo:** no real IP addresses (use `192.168.1.50`), host names, e-mail addresses, user folder paths (use `C:\Users\<you>\`), keys or tokens. `tests/test_no_personal_info.py` fails on it.
4. **Don't commit, push, tag, deploy or release.** Leave your changes in the working tree; the manager does the rest. Don't change git settings.
5. **No new dependencies** and no changes to firewall, security or system settings.
6. **Don't weaken a safety limit** (`subtune/guard.py`, `subtune/legal.py`) or a test to make something pass. If a test is wrong, say so in your report instead.

## Work in small steps

- One spec, one step at a time. Finish and check a step before the next. A step should change at most a few files.
- Your window is 128k tokens, but quality and speed drop as it fills. **Don't open big files whole.** `server.py` is thousands of lines (about 35k tokens): search first (`grep -n "def name"`), then read about 150 lines around the match. Never print whole logs or test output; use `tail -20`. Start a fresh session for each spec step instead of carrying one long conversation.
- Keep new modules under 400 lines and functions under 60 (D6 in the roadmap). Leave a file smaller than you found it when you can.
- Match the surrounding code: names, error messages in plain English for non-experts, feet for lengths shown to the owner, meters inside.
- Comment only the reason the code can't show.

## How to check your work

On Windows (PowerShell), from the repo folder:

```
& "$env:LOCALAPPDATA\subtune-venv\Scripts\python.exe" tests\test_X.py          # one test file, prints N/N passed
& "$env:LOCALAPPDATA\subtune-venv\Scripts\python.exe" -m pyflakes subtune\     # static check, no output = clean
& "$env:LOCALAPPDATA\subtune-venv\Scripts\python.exe" tests\test_compile.py
& "$env:LOCALAPPDATA\subtune-venv\Scripts\python.exe" tests\test_js_globals.py  # after any change to subtune\web\js
```

Each test file runs on its own. Run the tests for what you touched, plus the three checks above. The manager runs the whole suite and the browser check (`tests/browser_check.py`) before pushing.

**Write the test first** for new behavior (a small `tests/test_<area>.py`, same style as the existing ones: `test_` functions, an `if __name__` runner printing `N/N passed`, temp data via `BASSBLEND_DATA` / `BASSBLEND_CONFIG`). A step isn't done until its test fails without your change and passes with it.

## Be honest

- **Never say something is done, fixed, saved or passing unless you ran it and saw it.** Local models have a habit of claiming actions they didn't take; the owner relies on your report. If you couldn't run something, say "not run".
- If a spec is unclear, or you'd have to guess a fact, stop and write the question in your report rather than inventing.

## Adding things

- **A new assistant tool:** an entry in `assistant.py` (`_t(...)`), an executor in the tool map (`build_executors` in `server.py`), a `_brief` label, a `DESCRIBE` entry if it needs approval, and a line in `guard.SOUND` or `guard.CHANGES` if it plays sound or changes anything. `tests/test_coach.py` and `tests/test_guard.py` check this.
- **A new page:** a card in `index.html`, an entry in `MENU` in `js/nav.js`, render code in the right `js/` part, a section in `subtune/web/manual.html`.
- **A new setting:** add it to `SETTABLE` (or validate it where it's saved) with a range, and document it in the manual.

## Your report when you finish a step

Four short parts: **Changed** (files and what), **Tests run** (commands and results, copied), **Not run / unverified**, **Questions**. Nothing else; the manager reads it and checks the work itself.
