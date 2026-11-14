"""htTamer (command: subtune) - automatic multi-sub tuning for the miniDSP 2x4HD.

Typical run (Claude drives this; the dashboard shows each step live):
  subtune setup --cal <file> --preset 4 --subs 1,2,3,4
  subtune prepare          # take over the preset, neutral settings, source=USB
  subtune discover         # which outputs reach the mic
  subtune level            # set a safe sweep level
  subtune selftest         # prove PEQ writes land where we think
  subtune measure --pos 1  # repeat for each mic position
  subtune optimize
  subtune apply
  subtune verify --pos 1
  subtune restore          # back to the original source
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import numpy as np

from .config import DATA, MEAS_DIR, load_settings, save_settings
from .state import busy, event, load_state, update_state


def _outs(txt):            # user-facing 1-based -> 0-based
    return [int(x) - 1 for x in txt.split(",") if x.strip()]


def cmd_status(a):
    from .dsp import MiniDSP
    d = MiniDSP()
    if not d._url():
        print("probing USB (slow, one time)...")
        print(d.probe())
    st = d.status()
    update_state(dsp_status=st, dsp_status_t=time.time())
    print(json.dumps(st, indent=2))


def cmd_setup(a):
    s = load_settings()
    if a.cal:
        s["cal_file"] = a.cal
    if a.preset:
        s["preset"] = a.preset - 1
    if a.subs:
        s["subs"] = _outs(a.subs)
    for k in ("fmin", "fmax", "house_db", "house_fc", "max_boost_db", "global_peq_bands", "sub_peq_bands"):
        v = getattr(a, k)
        if v is not None:
            s[k] = v
    save_settings(s)
    update_state(settings=s)
    event("config", "settings updated", settings={k: s[k] for k in ("cal_file", "preset", "subs", "fmin", "fmax",
                                                                   "house_db", "max_boost_db")})
    print(json.dumps(s, indent=2))


def _rig():
    from .measure import Rig
    return Rig()


def cmd_prepare(a):
    s = load_settings()
    if s.get("preset") is None or not s.get("subs"):
        sys.exit("run `setup --preset N --subs a,b,c` first")
    with busy(f"prepare preset {s['preset'] + 1}"):
        _rig().prepare(s["preset"], s["subs"])


def cmd_discover(a):
    with busy("discover outputs"):
        r = _rig().discover()
    print(json.dumps(r, indent=2))


def cmd_level(a):
    with busy("set sweep level"):
        print(_rig().level(target_snr=a.snr))


def cmd_selftest(a):
    s = load_settings()
    out = _outs(a.output)[0] if a.output else s["subs"][0]
    with busy(f"self-test PEQ on output {out + 1}"):
        ok, m = _rig().selftest(out)
    print("OK" if ok else "FAILED", round(m, 2))
    if not ok:
        sys.exit(2)


def cmd_allspeakers(a):
    """Experimental: level, distance and polarity of every bed speaker from a 7.1 file the owner plays."""
    from . import allspk
    try:
        with busy(f"all-speakers check at spot {a.pos}"):
            allspk.run(a.pos, a.mode, auto_volume=not a.no_auto_volume, avr_input=a.avr_input)
    except Exception as e:
        update_state(allspk_status={"running": False, "error": str(e)})
        raise


def cmd_headroom(a):
    """How loud one sub output can play cleanly (rising tone bursts with automatic stops)."""
    from . import headroom
    s = load_settings()
    out = a.output - 1
    if out not in s.get("subs", []):
        sys.exit(f"output {a.output} is not a sub output")
    with busy(f"headroom test on output {a.output}"):
        rig = _rig()
        _restoring(rig, lambda: headroom.run(rig, out))


def cmd_tone(a):
    s = load_settings()
    out = a.output - 1
    if out not in s.get("subs", []):
        sys.exit(f"output {a.output} is not a sub output")
    if not 20 <= a.freq <= 200 or not 1 <= a.seconds <= 10 or (a.dbfs is not None and not -60 <= a.dbfs <= -10):
        sys.exit("tone limits: 20-200 Hz, 1-10 s, -60..-10 dBFS")
    with busy(f"test tone on output {a.output}"):
        r = _rig().tone(out, a.freq, a.seconds, a.dbfs)
    print(json.dumps(r))


def cmd_measure(a):
    with busy(f"measure position {a.pos}"):
        H, q = _rig().measure_position(a.pos)
    print(json.dumps({str(k): v for k, v in q.items()}, indent=2))


def cmd_clear(a):
    for f in MEAS_DIR.glob("pos*.npz"):
        f.unlink()
    update_state(measurements={}, result=None, verify={})
    event("config", "cleared all measurements")


def cmd_optimize(a):
    from .measure import load_measurements
    from .optimize import optimise
    subs, Hs, names = load_measurements()
    with busy(f"optimise {len(subs)} subs x {len(names)} positions"):
        r = optimise(Hs, subs, names)
    print(json.dumps({k: r[k] for k in ("subs", "peq_global", "headroom_db", "metrics")}, indent=2,
                     default=lambda o: o if not isinstance(o, tuple) else list(o)))


def full_slot_cmds(d, slot0, r, lpf=None):
    """Every write needed to make a DSP slot hold exactly this tune: the DSP
    can't report what's already there, so nothing is left to chance."""
    from .config import N_OUTPUTS
    subs = [x["output"] for x in r["subs"]]
    cmds = [d.c_preset(slot0)]
    for i in (0, 1):
        cmds += [f"input {i} gain -- 0", f"input {i} mute off", f"input {i} peq all bypass on"]
        for o in range(N_OUTPUTS):
            cmds.append(d.c_routing(i, o, o in subs))
            if o in subs:
                cmds.append(d.c_routing_gain(i, o, 0))
    for o in range(N_OUTPUTS):
        sub = next((x for x in r["subs"] if x["output"] == o), None)
        if sub:
            cmds += d.write_sub_filters(o, sub["gain_db"], sub["delay_ms"], sub["invert"], sub["biquads"], lpf)
            cmds += [f"output {o} fir bypass on", f"output {o} compressor -b on", d.c_out_mute(o, False)]
        else:
            cmds.append(d.c_out_mute(o, True))
    return cmds


def cmd_apply(a):
    from . import library
    from .dsp import MiniDSP
    from .biquad import lr4_lowpass, to_minidsp
    s = load_settings()
    if a.tune:
        tune = library.get(a.tune)
        r, name = tune["result"], tune["name"]
    else:                                                   # the current optimiser result
        r = json.loads((DATA / "result.json").read_text())
        name = None
    slot0 = (a.slot - 1) if a.slot else s["preset"]
    if not 0 <= slot0 <= 3:
        sys.exit("slot must be 1-4")
    if slot0 == library.ORIGINAL_SLOT and not a.allow_original:
        sys.exit("slot 1 holds your original setup; pass --allow-original to overwrite it")
    d = MiniDSP(s)
    lpf = [to_minidsp(*bq) for bq in lr4_lowpass(a.lpf)] if a.lpf else None
    cmds = full_slot_cmds(d, slot0, r, lpf)
    with busy(f"apply tune to slot {slot0 + 1}"):
        # every applied tune lives in the library (same filters are only stored once)
        saved = library.save(r, name or time.strftime("Tune %b %d, %I:%M %p"), settings={
            k: s.get(k) for k in ("fmin", "fmax", "house_db", "house_fc", "max_boost_db", "mlp_weight",
                                  "nearfield_max_cut_db", "nearfield_max_boost_db", "nearfield_max_eq_cut_db")})
        d.batch(cmds, f"apply '{saved['name']}' to slot {slot0 + 1} ({len(cmds)} writes)")
        library.record_slot(slot0 + 1, saved["id"], saved["name"])
        now = time.time()
        with open(DATA / "applied_history.jsonl", "a") as f:
            f.write(json.dumps({"t": now, "preset": slot0, "tune": saved["id"], "result": r}) + "\n")
        # the dashboard's "current result" becomes whatever is now playing
        cur = dict(r, applied=now, lpf_hz=a.lpf, slot=slot0 + 1, tune_id=saved["id"], tune_name=saved["name"])
        (DATA / "result.json").write_text(json.dumps(cur, indent=2))
        st = load_state()
        prev = st.get("result") or {}
        same = bool(prev.get("subs")) and library._fingerprint(prev) == saved["fingerprint"]
        verify, meta = st.get("verify") or {}, st.get("verify_meta") or {}
        if not same:                                       # an old verify no longer describes the DSP
            verify.pop("after", None)
            meta = {}
        update_state(result=cur, verify=verify, verify_meta=meta)
        event("config", f"slot {slot0 + 1} now holds '{saved['name']}' and is the active preset")
        from . import journal
        ma = (cur.get("metrics") or {}).get("after") or {}
        journal.add("tune", f"Applied '{saved['name']}' to slot {slot0 + 1}"
                    + (f": predicted MLP flatness ±{ma['mlp_flat_rms_db']:.1f} dB, all seats ±{ma['flat_rms_db']:.1f} dB"
                       if ma.get("mlp_flat_rms_db") is not None and ma.get("flat_rms_db") is not None else ""),
                    tune_id=saved["id"], slot=slot0 + 1)
        try:                                               # seats measured with the old tune go stale
            from . import blendmulti
            blendmulti.refresh()
        except Exception:
            pass


def cmd_blendseats(a):
    """Re-run the multi-seat blend optimiser on the saved seats (no sound)."""
    from . import blendmulti
    m = blendmulti.refresh()
    print(json.dumps({k: m[k] for k in ("seats", "now_db", "best", "dsp_only", "level_err_db")} if m else None, indent=2))


def cmd_avrblend(a):
    from . import avrmeasure
    try:
        with busy(f"AVR blend test at spot {a.pos}"):
            avrmeasure.run(a.mode, a.pos, speakers=a.speakers, auto_volume=not a.no_auto_volume, avr_input=a.avr_input)
    except Exception as e:
        update_state(avr_blend_status={"running": False, "error": str(e)})
        raise


def cmd_deepcheck(a):
    """Full-range system report through the receiver (left, right, both)."""
    from . import deepcheck
    try:
        with busy(f"system report at spot {a.pos}"):
            deepcheck.run(a.mode, a.pos, auto_volume=not a.no_auto_volume, avr_input=a.avr_input)
    except Exception as e:
        update_state(deep_status={"running": False, "error": str(e)})
        raise


def cmd_fixup(a):
    """Act on the latest system report: sub level, blend fix, then check again."""
    from . import fixup
    try:
        with busy(f"fixes at spot {a.pos}"):
            fixup.run(a.pos, a.mode, avr_input=a.avr_input)
    except Exception as e:
        update_state(fix_status={"running": False, "error": str(e)})
        raise


def blend_tune(cur, b, seats_txt="the MLP"):
    """The playing tune with a blend fix baked in: (new result, name, notes).
    b: {"delay_ms", "invert", "allpass": None | {"fc", "q"}}. Negative delays are
    a receiver setting, so they're ignored here. Raises ValueError if there's
    nothing the miniDSP can change or no EQ band is free for the phase filter."""
    from .blendmulti import allpass_minidsp
    from .config import PEQ_BANDS
    d = b["delay_ms"] if b["delay_ms"] > 0 else 0.0
    ap = b.get("allpass")
    if d == 0 and not b["invert"] and not ap:
        raise ValueError("nothing to change in the miniDSP (timing fixes for late subs are a receiver setting)")
    new = json.loads(json.dumps(cur))
    # a blend fix only shifts the subs' timing, so remember which sub tune it came from
    new["base_tune_id"] = cur.get("base_tune_id") or cur.get("tune_id")
    for k in ("applied", "slot", "tune_id", "tune_name", "lpf_hz"):
        new.pop(k, None)
    for x in new["subs"]:
        x["delay_ms"] = round(x["delay_ms"] + d, 3)
        if b["invert"]:
            x["invert"] = not x["invert"]
        if ap:
            if len(x["biquads"]) >= PEQ_BANDS:
                raise ValueError(f"output {x['output'] + 1} has no free EQ band for the phase filter")
            x["biquads"] = list(x["biquads"]) + [allpass_minidsp(ap["fc"], ap["q"])]
            x["allpass"] = list(x.get("allpass") or []) + [{"fc": ap["fc"], "q": ap["q"]}]
    parts = ([f"+{d:g} ms"] if d else []) + (["inverted"] if b["invert"] else []) +             ([f"all-pass {ap['fc']:.0f} Hz"] if ap else [])
    name = f"{cur.get('tune_name') or 'Tune'} + blend ({', '.join(parts)})"
    ap_txt = f", all-pass {ap['fc']:.0f} Hz Q {ap['q']}" if ap else ""
    flip_txt = ", polarity flipped" if b["invert"] else ""
    return new, name, f"Blend with the speakers ({seats_txt}): subs delayed {d:g} ms{flip_txt}{ap_txt}."


def cmd_avrapply(a):
    """Bake the blend fix (one seat, or all measured seats) into a new tune on the playing slot."""
    from . import library
    st = load_state()
    cur = st.get("result")
    if not cur or not cur.get("subs"):
        sys.exit("apply a sub tune first")
    if getattr(a, "multi", False):
        m = st.get("avr_blend_multi")
        if not m or m.get("tune_id") != cur.get("tune_id"):
            sys.exit("measure the blend at one or more seats with the tune that's playing first")
        b = m["dsp_only"]
        seats_txt = f"{len(m['seats'])} seat{'s' if len(m['seats']) > 1 else ''}"
    else:
        b = st.get("avr_blend")
        if not b:
            sys.exit("run the AVR blend test first")
        if b.get("tune_id") is not None and b.get("tune_id") != cur.get("tune_id"):
            sys.exit("that blend test was measured with a different tune; run it again first")
        seats_txt = "the MLP" if b.get("pos", 1) == 1 else f"spot {b.get('pos')}"
    try:
        new, name, notes = blend_tune(cur, b, seats_txt)
    except ValueError as e:
        sys.exit(str(e))
    t = library.save(new, name, notes)
    a.tune, a.slot, a.lpf, a.allow_original = t["id"], cur.get("slot") or (load_settings()["preset"] + 1), None, False
    cmd_apply(a)
    if not getattr(a, "multi", False):         # a single-seat fix is used up once applied
        update_state(avr_blend=dict(b, applied_as=t["id"]))


def cmd_slot(a):
    """Switch which DSP preset is playing (A/B listening)."""
    from .dsp import MiniDSP
    if not 1 <= a.n <= 4:
        sys.exit("slot must be 1-4")
    d = MiniDSP(load_settings())
    d.batch([d.c_preset(a.n - 1)], f"active preset -> slot {a.n}")


def _restoring(rig, fn):
    """Run fn on the USB input, then hand the subs back to whatever input was active."""
    before = rig.dsp.status()["master"]["source"].lower()
    try:
        return fn()
    finally:
        if before != "usb":
            rig.dsp.batch([rig.dsp.c_source(before)] + rig.mute_except(rig.subs),
                          f"done: input back to {'AVR (analog)' if before == 'i2s' else before}")


def cmd_checkup(a):
    with busy(f"check-up at spot {a.pos}"):
        rig = _rig()
        r = _restoring(rig, lambda: rig.checkup(a.pos))
    print(json.dumps({k: r[k] for k in ("noise_spl", "test_spl", "snr_db", "peak_dbfs")}))


def cmd_levelmatch(a):
    with busy("sub level match"):
        rig = _rig()
        r = _restoring(rig, rig.level_match)
    print(json.dumps(r))


def cmd_verify(a):
    with busy(f"verify at position {a.pos}"):
        rig = _rig()
        before = rig.dsp.status()["master"]["source"].lower() if a.restore else None
        try:
            rig.measure_combined("after", a.pos)
            from . import journal
            journal.add("verify", f"Verified the playing tune at spot {a.pos} (measured with all subs on)")
        finally:
            if before and before != "usb":             # hand the subs back to the AVR
                rig.dsp.batch([rig.dsp.c_source(before)] + rig.mute_except(rig.subs),
                              f"verify done: input back to {'AVR (analog)' if before == 'i2s' else before}")


def cmd_baseline(a):
    with busy(f"baseline at position {a.pos}"):
        _rig().measure_combined("before", a.pos)


def cmd_restore(a):
    with busy("restore source"):
        _rig().restore_source()


def cmd_unmute(a):
    """Silent: unmute every sub output (used after a stopped run)."""
    from .dsp import MiniDSP
    s = load_settings()
    d = MiniDSP(s)
    d.batch([d.c_out_mute(o, False) for o in s["subs"]], "unmute all subs")


def cmd_simulate(a):
    """Synthetic room for testing the optimiser + dashboard without hardware."""
    from .audio import GRID
    from .measure import MEAS_DIR
    rng = np.random.default_rng(a.seed)
    S, P = a.subs, a.positions
    modes = [(f, q) for f, q in zip(rng.uniform(25, 160, 14), rng.uniform(4, 14, 14))]
    MEAS_DIR.mkdir(parents=True, exist_ok=True)
    for f in MEAS_DIR.glob("pos*.npz"):
        f.unlink()
    sub_pos = rng.uniform(0, 1, (S, 3))
    meas = {}
    from .audio import smooth_db
    for p in range(P):
        mic = np.array([0.5, 0.6, 0.4]) + rng.normal(0, 0.06, 3)
        H = []
        for i in range(S):
            h = np.zeros_like(GRID, dtype=complex)
            for k, (fm, q) in enumerate(modes):
                shape = np.cos(np.pi * (k % 3 + 1) * sub_pos[i]).prod() * np.cos(np.pi * (k % 3 + 1) * mic).prod()
                h += shape / (1 - (GRID / fm) ** 2 + 1j * GRID / (q * fm))
            h += 0.6                                           # direct/diffuse field
            dist = np.linalg.norm((sub_pos[i] - mic) * [6, 5, 2.6])
            h *= np.exp(-2j * np.pi * GRID * dist / 343) / max(dist, 0.5)
            h *= (1j * GRID / 22) ** 2 / (1 + 1j * GRID / (22 * 0.7) - (GRID / 22) ** 2)   # sub HPF
            h *= 1 / (1 + 1j * GRID / 250)
            H.append(h * 10 ** (-40 / 20))
        np.savez(MEAS_DIR / f"pos{p + 1}.npz", grid=GRID, subs=np.arange(S), H=np.array(H))
        meas[str(p + 1)] = {"subs": list(range(S)),
                            "db": {str(i): np.round(smooth_db(H[i], 12), 2).tolist() for i in range(S)},
                            "quality": {str(i): {"snr_db": 60.0, "simulated": True} for i in range(S)}}
    update_state(measurements=meas, grid=np.round(GRID, 3).tolist(), result=None, simulated=True)
    event("config", f"simulated {S} subs x {P} positions (no hardware touched)")


def cmd_analysis_context(a):
    from .analysis import build_context
    print(json.dumps(build_context(), indent=1))


def cmd_set_analysis(a):
    from .analysis import store_external
    store_external(open(a.file, encoding="utf-8").read(), a.source)


def cmd_analyze(a):
    from .analysis import run_claude
    r = run_claude(a.question)
    print(r.get("error") or r["markdown"])


def cmd_serve(a):
    from .server import serve
    serve(a.port, lan=a.lan)


def cmd_set_pin(a):
    """Choose the PIN that protects the dashboard in network mode."""
    import getpass
    from . import auth
    if a.stdin:
        pin = sys.stdin.readline().strip()
    else:
        pin = getpass.getpass("New PIN (6+ characters): ")
        if getpass.getpass("Same PIN again: ") != pin:
            sys.exit("The two PINs didn't match; nothing changed.")
    try:
        auth.set_pin(pin)
    except ValueError as e:
        sys.exit(str(e))
    print("PIN saved. Anyone signed in on another device will need to sign in again.")



def cmd_export_config(a):
    """Write a settings file (room, subs, speakers, mic file, tunes) to carry to another device."""
    from pathlib import Path
    from . import bundle
    b = bundle.export(include_history=not a.no_history, include_pin=a.include_pin, include_key=a.include_key)
    out = Path(a.out or bundle.filename())
    out.write_text(bundle.dumps(b), encoding="utf-8")
    try:
        out.chmod(0o600 if b.get("secrets") else 0o644)
    except OSError:
        pass
    print(f"Saved {out} ({out.stat().st_size // 1024} KB)"
          + (" - it contains secrets, keep it private" if b.get("secrets") else ""))


def cmd_import_config(a):
    """Merge a settings file into this device."""
    from pathlib import Path
    from . import bundle
    try:
        r = bundle.import_bundle(bundle.loads(Path(a.file).read_text(encoding="utf-8")))
    except (OSError, ValueError) as e:
        sys.exit(f"Couldn't import: {e}")
    print("Imported: " + ", ".join(r["imported"]))

def main(argv=None):
    p = argparse.ArgumentParser(prog="subtune", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("status").set_defaults(fn=cmd_status)
    s = sp.add_parser("setup")
    s.add_argument("--cal"); s.add_argument("--preset", type=int, help="1-4")
    s.add_argument("--subs", help="1-based outputs, e.g. 1,2,3,4")
    for k in ("fmin", "fmax", "house_db", "house_fc", "max_boost_db"):
        s.add_argument("--" + k.replace("_", "-"), dest=k, type=float)
    for k in ("global_peq_bands", "sub_peq_bands"):
        s.add_argument("--" + k.replace("_", "-"), dest=k, type=int)
    s.set_defaults(fn=cmd_setup)
    sp.add_parser("prepare").set_defaults(fn=cmd_prepare)
    sp.add_parser("discover").set_defaults(fn=cmd_discover)
    s = sp.add_parser("level"); s.add_argument("--snr", type=float, default=40); s.set_defaults(fn=cmd_level)
    s = sp.add_parser("selftest"); s.add_argument("--output"); s.set_defaults(fn=cmd_selftest)
    s = sp.add_parser("measure"); s.add_argument("--pos", type=int, required=True); s.set_defaults(fn=cmd_measure)
    sp.add_parser("clear").set_defaults(fn=cmd_clear)
    sp.add_parser("optimize").set_defaults(fn=cmd_optimize)
    s = sp.add_parser("apply"); s.add_argument("--lpf", type=float, help="optional LR4 low-pass Hz")
    s.add_argument("--tune", help="library tune id (default: current result)")
    s.add_argument("--slot", type=int, help="DSP slot 1-4 (default: the preset htTamer owns)")
    s.add_argument("--allow-original", action="store_true", help="allow overwriting slot 1")
    s.set_defaults(fn=cmd_apply)
    s = sp.add_parser("slot"); s.add_argument("--n", type=int, required=True); s.set_defaults(fn=cmd_slot)
    s = sp.add_parser("avrblend"); s.add_argument("--mode", choices=["hdmi", "dlna", "manual"], default="dlna",
                   help="hdmi = the Pi plays it out of its HDMI port; dlna = the receiver's network player; manual = USB stick")
    s.add_argument("--avr-input", default=None, help="receiver input the Pi's HDMI is plugged into (hdmi mode)")
    s.add_argument("--pos", type=int, default=1)
    s.add_argument("--speakers", choices=["L", "LR"], default="L", help="L = left only, LR = left then right")
    s.add_argument("--no-auto-volume", action="store_true", help="leave the receiver volume as it is")
    s.set_defaults(fn=cmd_avrblend)
    s = sp.add_parser("deepcheck", help="full-range system report through the receiver")
    s.add_argument("--mode", choices=["hdmi", "dlna", "manual"], default="dlna",
                   help="hdmi = the Pi plays it out of its HDMI port; dlna = the receiver's network player; manual = USB stick")
    s.add_argument("--avr-input", default=None, help="receiver input the Pi's HDMI is plugged into (hdmi mode)")
    s.add_argument("--pos", type=int, default=1)
    s.add_argument("--no-auto-volume", action="store_true", help="leave the receiver volume as it is")
    s.set_defaults(fn=cmd_deepcheck)
    s = sp.add_parser("allspeakers", help="experimental: check every bed speaker with a 7.1 test file")
    s.add_argument("--pos", type=int, default=1)
    s.add_argument("--mode", choices=["hdmi", "manual"], default="hdmi",
                   help="hdmi = the Pi plays it out of its HDMI port; manual = you play it from another source")
    s.add_argument("--avr-input", default=None, help="receiver input code the Pi's HDMI is plugged into (e.g. 10 = BD/DVD)")
    s.add_argument("--no-auto-volume", action="store_true", help="leave the receiver volume as it is")
    s.set_defaults(fn=cmd_allspeakers)
    s = sp.add_parser("headroom", help="how loud one sub can play cleanly (loud; stops automatically)")
    s.add_argument("--output", type=int, required=True, help="1-based output")
    s.set_defaults(fn=cmd_headroom)
    s = sp.add_parser("fixup", help="fix what htTamer can from the latest system report, then check again")
    s.add_argument("--mode", choices=["hdmi", "dlna", "manual"], default="dlna",
                   help="hdmi = the Pi plays it out of its HDMI port; dlna = the receiver's network player; manual = USB stick")
    s.add_argument("--avr-input", default=None, help="receiver input the Pi's HDMI is plugged into (hdmi mode)")
    s.add_argument("--pos", type=int, default=1)
    s.set_defaults(fn=cmd_fixup)
    s = sp.add_parser("avrapply"); s.add_argument("--multi", action="store_true", help="use the multi-seat blend")
    s.set_defaults(fn=cmd_avrapply)
    sp.add_parser("blendseats").set_defaults(fn=cmd_blendseats)
    s = sp.add_parser("baseline"); s.add_argument("--pos", type=int, required=True); s.set_defaults(fn=cmd_baseline)
    s = sp.add_parser("verify"); s.add_argument("--pos", type=int, required=True)
    s.add_argument("--restore", action="store_true", help="put the input back afterwards")
    s.set_defaults(fn=cmd_verify)
    sp.add_parser("restore").set_defaults(fn=cmd_restore)
    sp.add_parser("unmute").set_defaults(fn=cmd_unmute)
    s = sp.add_parser("checkup"); s.add_argument("--pos", type=int, default=1); s.set_defaults(fn=cmd_checkup)
    sp.add_parser("levelmatch").set_defaults(fn=cmd_levelmatch)
    s = sp.add_parser("tone", help="test tone on one sub output")
    s.add_argument("--output", type=int, required=True, help="1-based output")
    s.add_argument("--freq", type=float, default=50.0)
    s.add_argument("--seconds", type=float, default=3.0)
    s.add_argument("--dbfs", type=float)
    s.set_defaults(fn=cmd_tone)
    sp.add_parser("analysis-context").set_defaults(fn=cmd_analysis_context)
    s = sp.add_parser("set-analysis"); s.add_argument("--file", required=True)
    s.add_argument("--source", default="Claude Code"); s.set_defaults(fn=cmd_set_analysis)
    s = sp.add_parser("analyze"); s.add_argument("--question"); s.set_defaults(fn=cmd_analyze)
    s = sp.add_parser("simulate"); s.add_argument("--subs", type=int, default=4)
    s.add_argument("--positions", type=int, default=5); s.add_argument("--seed", type=int, default=3)
    s.set_defaults(fn=cmd_simulate)
    s = sp.add_parser("serve"); s.add_argument("--port", type=int, default=8765)
    s.add_argument("--lan", action="store_true", help="serve your home network (needs a PIN, see set-pin)")
    s.set_defaults(fn=cmd_serve)
    s = sp.add_parser("set-pin", help="set the dashboard PIN for network mode")
    s.add_argument("--stdin", action="store_true", help="read the PIN from standard input (for setup scripts)")
    s.set_defaults(fn=cmd_set_pin)
    s = sp.add_parser("export-config", help="save room, speaker, sub and tune settings to a file")
    s.add_argument("--out", help="file to write (default: bassblend-config-<host>-<date>.json)")
    s.add_argument("--no-history", action="store_true", help="leave out tunes, results and measurements")
    s.add_argument("--include-pin", action="store_true", help="include the PIN (as its hash)")
    s.add_argument("--include-key", action="store_true", help="include the Anthropic API key")
    s.set_defaults(fn=cmd_export_config)
    s = sp.add_parser("import-config", help="load a settings file saved by export-config or the dashboard")
    s.add_argument("file")
    s.set_defaults(fn=cmd_import_config)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
