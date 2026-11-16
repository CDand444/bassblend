# Spec 04: type hints and mypy on the safety modules

**Goal:** the modules that guard the owner's equipment are fully type-annotated and checked by mypy on every push.

**Why:** a wrong argument type only shows when the code runs, and small coding models make that mistake more. These modules enforce the safety rules, so they get checked first. See `docs/dev/ROADMAP.md`, item 3.

## Modules (in this order)

`subtune/legal.py`, `guard.py`, `limits.py`, `abtest.py`, `ha.py`, `feedback.py`, `fixlog.py`, `automation.py`, `shape.py`, `update.py`.

## Steps

1. Add `mypy.ini` at the repo root:
   ```ini
   [mypy]
   python_version = 3.12
   ignore_missing_imports = True
   follow_imports = silent
   warn_unused_ignores = True
   files = subtune/legal.py, subtune/guard.py, subtune/limits.py, subtune/abtest.py, subtune/ha.py, subtune/feedback.py, subtune/fixlog.py, subtune/automation.py, subtune/shape.py, subtune/update.py

   [mypy-subtune.legal]
   disallow_untyped_defs = True
   ```
   Add one `[mypy-subtune.<module>]` block with `disallow_untyped_defs = True` per module as you finish it, in the order above (one module per step).
2. For each module: annotate every function (arguments and return), fix what mypy finds, and **don't change behaviour**. If mypy points at a real bug, fix it with a test and say so in your report. Don't silence errors with `# type: ignore` unless unavoidable, and explain each one in a comment.
3. Install mypy in the dev environment (`pip install mypy`; pin the version in the CI step, not in `requirements.txt`, which is only for runtime).
4. When all modules pass, the manager adds `python -m mypy` to the Linux job in `.github/workflows/ci.yml`.

## Tests and checks

- `python -m mypy` prints "Success" with no errors.
- Every existing test file still passes (annotation-only changes must not alter behaviour); `pyflakes` stays clean.
- A tiny test, `tests/test_typecheck.py`: runs `python -m mypy` through `subprocess` when mypy is installed, asserts exit code 0, and otherwise prints a skip note and passes.

## Out of scope

Annotating the whole codebase, changing runtime code for the sake of typing, adding mypy to `requirements.txt`.
