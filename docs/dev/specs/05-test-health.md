# Spec 05: a fast, steady test suite

**Goal:** the whole offline suite (about 45 files) runs in under 4 minutes on a laptop and never fails by chance.

**Why:** it takes about 10 minutes on Windows today, and `tests/test_mcp.py` occasionally fails with `ConnectionAbortedError: [WinError 10053]` (in `test_dashboard_needs_a_credential_even_from_this_computer`, and once in another test of the same file) and then passes on a rerun. Slow and flaky tests get skipped. See `docs/dev/ROADMAP.md`, item 2.

## Steps

1. **Measure.** Write `tests/time_tests.py`: runs every `tests/test_*.py` as its own process (same interpreter, a per-file timeout of 300 s), prints a table sorted by seconds (file, seconds, result), and the total. Run it and put the top 10 in your report.
2. **Find the flake.** Reproduce `test_mcp.py`'s failure by running it in a loop (30 runs). Look at how the test's HTTP client talks to the server (`http.client`): the likely cause is the server closing a connection before the client reads the response (an unread request body, or a keep-alive/`Connection: close` mismatch). Fix the root cause in the test helper or, if the server really misbehaves, in `subtune/server.py` (`_send`, how the body is read) with a test. A retry that hides it is not a fix.
3. **Speed up.** For each slow file: remove real `sleep`s (use short timeouts or inject a clock), avoid starting servers or subprocesses per test when one per file will do, and never touch the network. Keep every test's meaning.
4. **Run in parallel.** Extend `tests/time_tests.py` (or add `tests/run_all.py`) with a `--parallel N` option running files in separate processes with separate temp data folders. First check that no test uses a fixed port or a shared folder; fix any that do.

## Definition of done

- `python tests/run_all.py --parallel 4` runs the whole suite in under 4 minutes and prints "all passed".
- `tests/test_mcp.py` passes 30 times in a row.
- No test lost coverage: report the number of `test_` functions before and after (it must not go down).
- `pyflakes` clean; `tests/test_js_globals.py` and `tests/test_no_personal_info.py` unchanged.

The manager may switch `.github/workflows/ci.yml` to use the new runner afterwards.

## Out of scope

Rewriting tests, a new test framework, changing what the suite covers.
