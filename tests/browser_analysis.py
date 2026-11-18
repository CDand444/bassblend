r"""Browser check of the Bass analysis page (Verify → Bass analysis) with seeded measurements: the waterfall draws, the ring times
name the room mode, the trust check reads the take-to-take difference, and the blend phase switches between as measured and the fix.

Starts htTamer with synthetic measurement files (no sound, no receiver, no miniDSP). Needs Playwright.
Run:  python tests/browser_analysis.py            (not part of the offline tests: it needs a browser)
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import browser_check as bc                                   # noqa: E402
from browser_actions import PROBLEMS, check, until          # noqa: E402
from subtune.audio import GRID                              # noqa: E402


def mode(f0, q):
    s = 1j * GRID / f0
    return 1 / (1 + s / q + s * s)


def seed(data: pathlib.Path):
    (data / "measurements").mkdir(parents=True, exist_ok=True)
    H = np.stack([0.4 + mode(38.0, 22), 0.4 + mode(55.0, 8)])                  # two subs; the first excites a sharp 38 Hz mode
    for p in (1, 2):
        np.savez(data / "measurements" / f"pos{p}.npz", grid=GRID, subs=np.array([0, 1]), H=H * (1 if p == 1 else 0.9))
    rep = np.where((GRID > 60) & (GRID < 75), 2.4, 0.3).round(1).tolist()          # spot 1: two takes disagreed at 60-75 Hz
    st = {"measurements": {"1": {"subs": [0, 1], "db": {}, "quality": {}, "repeat_db": rep}, "2": {"subs": [0, 1], "db": {}, "quality": {}}},
          "grid": np.round(GRID, 3).tolist(),
          "result": {"applied": 1.0, "slot": 3, "tune_id": "T1", "subs": [{"output": 0, "gain_db": -3, "delay_ms": 0, "invert": False, "biquads": []},
                                                                           {"output": 1, "gain_db": -3, "delay_ms": 2, "invert": False, "biquads": []}]}}
    from subtune import livecheck                                               # a finished live music check (synthetic: no hardware)
    rng = np.random.default_rng(5)
    x = rng.standard_normal(48000 * 8) * 0.2
    y = np.concatenate([np.zeros(48000), x * 0.5, np.zeros(48000)]) + 0.002 * rng.standard_normal(48000 * 10)
    st["live_check"] = {**livecheck.analyze(x, y), "t": 1.8e9, "tune_id": "T1"}
    (data / "state.json").write_text(json.dumps(st))
    lp = 1 / (1 + 1.414 * (1j * GRID / 80) + (1j * GRID / 80) ** 2)
    (data / "blend").mkdir(exist_ok=True)
    np.savez(data / "blend" / "seat1.npz", Hm=(1j * GRID / 80) ** 2 * lp, Hs=lp * np.exp(-2j * np.pi * GRID * 0.006), t=0.0, tune_id="T1")


def main():
    from playwright.sync_api import sync_playwright
    port = bc.free_port()
    server, tmp = bc.start_server(port)
    base = f"http://127.0.0.1:{port}"
    try:
        seed(pathlib.Path(tmp) / "data")
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1300, "height": 1000})
            errs = []
            page.on("pageerror", lambda e: errs.append((e.stack or "") + " " + str(e)))       # the seeded tune is partial, so only this page's own errors count
            page.goto(base + "/#/analysis")
            page.wait_for_function("typeof MENU !== 'undefined' && typeof S !== 'undefined' && !!S.terms", timeout=20000)
            page.evaluate("async () => { await post('/api/terms', {accept: true, version: S.terms.version}); }")
            page.evaluate("setMode('advanced')")
            page.goto(base + "/#/analysis"); page.reload()
            check("Bass analysis: the waterfall draws from the stored sweeps", until(page, "!!anData && !!anData.waterfall && document.querySelector('#anWf').width > 100", 10000) is True)
            ring = page.evaluate("document.querySelector('#anRing').textContent")
            import re
            first = re.search(r"Longest: (\d+) Hz", ring)
            check("Bass analysis: the ring times name the room mode", bool(first) and 35 <= int(first.group(1)) <= 43, ring)
            check("Bass analysis: the trust check points at where the two takes disagreed", "60" in page.evaluate("document.querySelector('#anOut').textContent") and page.locator("#anTrust svg").count() == 1)
            page.select_option("#anPos", "2")
            check("Bass analysis: a spot without take-to-take data says so", until(page, "anData.pos === '2' && !anData.trust", 6000) is True)
            page.select_option("#anWhat", "1")
            check("Bass analysis: one sub alone", until(page, "anData.what === '1'", 6000) is True)
            check("Bass analysis: the blend phase is drawn", page.locator("#anBlend svg").count() == 1 and page.locator("#anPhase svg").count() == 1)
            before = page.evaluate("anData.blend[0].best.worst_phase_deg < anData.blend[0].measured.worst_phase_deg")
            page.click("[data-anbv='measured']")
            words = page.evaluate("document.querySelector('#anOut').textContent")
            check("Bass analysis: as measured, it shows the cancelling and the fix", before and "brings it to" in words, words[-300:])
            mine = [x for x in errs if "analysis.js" in x]
            words = page.evaluate("document.querySelector('#anOut').textContent")
            check("Live music check: the stored result is shown with its coherence", "coherence" in words and page.locator("#anLiveCoh svg").count() == 1, words[:300])
            check("Live music check: Start waits for a music file", page.evaluate("document.querySelector('#anLiveStart').disabled") is True)
            import tempfile
            from scipy.io import wavfile
            wav = pathlib.Path(tempfile.mkdtemp()) / "song.wav"
            wavfile.write(str(wav), 44100, (np.random.default_rng(2).standard_normal(44100 * 12) * 3000).astype(np.int16))
            page.set_input_files("#anMusic", str(wav))
            check("Live music check: a WAV is stored as the music", until(page, "!!anData.music && anData.music.seconds > 11 && !document.querySelector('#anLiveStart').disabled", 10000) is True)
            check("No script errors on this page", not mine, "; ".join(mine[:3]))
            browser.close()
    finally:
        server.kill()
    if PROBLEMS:
        sys.exit("FAILED: " + "; ".join(PROBLEMS))
    print("The Bass analysis page works.")


if __name__ == "__main__":
    main()
