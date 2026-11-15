"""What the receiver itself reports about its setup, decoded, and checked against htTamer's records.

Read-only eISCP queries (nothing is set). On the TX-RZ50 the network protocol gives:
  SPI  speaker configuration: sub, each speaker group's size (small/large/none), the
       crossover (or "per speaker"), where the two height pairs are, bi-amp
  SWL/CTL  sub and center level;  IFA/IFV  the live audio/video signal;  NRI/FWV  model, firmware
  TPD  internal temperature
It does NOT give speaker distances, per-speaker levels or per-speaker crossovers: on this
model those live only in the Speaker Setup menu (and Dirac Live writes them). The owner can
copy them onto the Speakers page; htTamer then checks them against the speaker positions.
"""
from __future__ import annotations

import math
import re
import time

SIZE = {"0": "none", "1": "small", "2": "large"}
SUBS = {"0": 0, "1": 1, "2": 2}
HEIGHT_POS = {"0": None, "1": "Front High", "2": "Top Front", "3": "Top Middle", "4": "Top Rear",
              "5": "Rear High", "6": "Dolby Enabled (front)", "7": "Dolby Enabled (surround)",
              "8": "Dolby Enabled (back)"}
HEIGHT_PREFIX = {"1": "FH", "2": "TF", "3": "TM", "4": "TR", "5": "RH", "6": "DF", "7": "DS", "8": "DB"}
BI_AMP = {"0": None, "1": "front", "3": "front + center", "5": "front + surround", "6": "center + surround",
          "7": "front + center + surround"}
GROUPS = ("front", "center", "surround", "surround_back", "height1", "height2")
GROUP_CH = {"front": ["FL", "FR"], "center": ["C"], "surround": ["SL", "SR"], "surround_back": ["BL", "BR"]}
DIST_TOL_FT = 0.5


def decode_spi(v: str | None) -> dict | None:
    """'1111111---240' -> sub, sizes, crossover, height positions, bi-amp (Onkyo/Pioneer SPI)."""
    if not v or not re.fullmatch(r"[0-9]{7}[0-9-]{3}[0-9]{3}", v):
        return None
    xo = v[7:10]
    out = {"subwoofer": SUBS.get(v[0], 0),
           "sizes": {g: SIZE.get(c, "?") for g, c in zip(GROUPS, v[1:7])},
           "crossover_hz": int(xo) if xo.isdigit() else None,
           "crossover_note": None if xo.isdigit() else "set per speaker",
           "height1_position": HEIGHT_POS.get(v[10]), "height2_position": HEIGHT_POS.get(v[11]),
           "height1_prefix": HEIGHT_PREFIX.get(v[10]), "height2_prefix": HEIGHT_PREFIX.get(v[11]),
           "bi_amp": BI_AMP.get(v[12], v[12]), "raw": v}
    return out


def channel_sizes(spi: dict) -> dict:
    """Per channel (FL, TFL, ...) size the receiver uses."""
    out = {}
    for g, chs in GROUP_CH.items():
        if spi["sizes"].get(g) not in (None, "none", "?"):
            out.update({c: spi["sizes"][g] for c in chs})
    for n in ("1", "2"):
        p, s = spi.get(f"height{n}_prefix"), spi["sizes"].get(f"height{n}")
        if p and s not in (None, "none", "?"):
            out.update({p + "L": s, p + "R": s})
    return out


def decode_ifa(v: str | None) -> dict | None:
    """Audio information: input, format, sample rate, input channels, listening mode, output channels."""
    if not v or v == "N/A":
        return None
    f = [x.strip() for x in v.split(",")]
    f += [""] * (7 - len(f))
    keys = ("input", "format", "sample_rate", "input_channels", "listening_mode", "output_channels", "output_rate")
    d = {k: (f[i] or None) for i, k in enumerate(keys)}
    d["raw"] = v
    return d


def decode_ifv(v: str | None) -> dict | None:
    if not v or v == "N/A":
        return None
    f = [x.strip() for x in v.split(",")] + [""] * 9
    return {"input": f[0] or None, "input_format": " ".join(x for x in f[1:4] if x) or None,
            "output": f[4] or None, "output_format": " ".join(x for x in f[5:8] if x) or None}


def parse_nri(xml: str | None) -> dict:
    out = {}
    for k in ("brand", "model", "year", "productid", "destination"):
        m = re.search(rf"<{k}>([^<]*)</{k}>", xml or "")
        if m:
            out[k] = m[1]
    out["atmos"] = bool(re.search(r'id="DolbyAtmos"[^>]*value="1"', xml or ""))
    out["dtsx"] = bool(re.search(r'id="DTS:X"[^>]*value="1"', xml or ""))
    return out


def read(o=None) -> dict:
    """Everything the receiver reports about its setup (read-only)."""
    from . import avr
    o = o or avr.Onkyo()
    got = {}
    for r in o._xfer(["PWRQSTN"]):
        got.setdefault(r[2:5], r[5:])
    if got.get("PWR") != "01":
        return {"t": time.time(), "power": got.get("PWR") == "01" if got.get("PWR") else None}
    for cmds, wait in ((["SPIQSTN", "SWLQSTN", "CTLQSTN", "IFAQSTN", "IFVQSTN", "FWVQSTN"], 4.0),
                       (["NRIQSTN", "TPDQSTN", "LMDQSTN", "SLIQSTN"], 4.0)):
        try:
            for r in o._xfer(cmds, wait=wait):
                got.setdefault(r[2:5], r[5:])
        except OSError:
            pass
    m = re.search(r"C\s*(-?\d+)", got.get("TPD") or "")
    return {"t": time.time(), "power": True, "device": parse_nri(got.get("NRI")),
            "firmware": got.get("FWV") if got.get("FWV") not in (None, "N/A") else None,
            "speakers": decode_spi(got.get("SPI")), "sub_level": avr.signed_half_db(got.get("SWL")),
            "center_level": avr.signed_half_db(got.get("CTL")), "audio": decode_ifa(got.get("IFA")),
            "video": decode_ifv(got.get("IFV")), "temp_c": int(m[1]) if m else None,
            "input": avr.INPUTS.get(got.get("SLI"), got.get("SLI")),
            "mode": avr.MODES.get(got.get("LMD"), got.get("LMD")),
            "not_readable": ["speaker distances", "per-speaker levels", "per-speaker crossovers"]}


def _dist_ft(a, b):
    return math.dist(a, b) / 0.3048


def check(details: dict, system: dict, speakers: dict, seats: list) -> list[dict]:
    """Compare what the receiver reports with htTamer's records. Each item: {status, text}."""
    out = []
    spi = (details or {}).get("speakers")
    if spi:
        beds = 2 + (spi["sizes"]["center"] != "none") + 2 * (spi["sizes"]["surround"] != "none") \
            + 2 * (spi["sizes"]["surround_back"] != "none")
        heights = 2 * (spi["sizes"]["height1"] != "none") + 2 * (spi["sizes"]["height2"] != "none")
        if system.get("beds") and system.get("heights") is not None and (system["beds"], system["heights"]) != (beds, heights):
            out.append({"status": "fix", "text": f"The receiver is set up for {beds}.x.{heights} speakers but htTamer has "
                        f"{system['beds']}.x.{system['heights']}. Correct the layout on the Receiver page (or the receiver's "
                        "Speaker Setup) so the tests and advice cover the right speakers."})
        if not spi["subwoofer"]:
            out.append({"status": "fix", "text": "The receiver says there is NO subwoofer, so it sends no bass to the sub "
                        "output and the miniDSP gets nothing. Set Subwoofer to Yes in Speaker Setup."})
        large = [g.replace("_", " ") for g, s in spi["sizes"].items() if s == "large"]
        if large:
            out.append({"status": "watch", "text": f"{', '.join(large).capitalize()} set to Large: those speakers also play the "
                        "deep bass instead of handing it to the subs. Small with a crossover (usually 80 Hz) lets the subs and "
                        "htTamer's tune handle it, which is what the blend test assumes."})
        if spi["crossover_note"]:
            out.append({"status": "info", "text": "Crossovers are set per speaker in the receiver, and its network protocol "
                        "can't report them. Copy them onto the Speakers page so the blend advice knows them."})
        elif spi["crossover_hz"]:
            out.append({"status": "info", "text": f"All speakers cross over to the subs at {spi['crossover_hz']} Hz."})
        if spi["bi_amp"]:
            out.append({"status": "info", "text": f"Bi-amp is on for: {spi['bi_amp']}."})
    # distances the owner copied from the receiver vs the recorded positions
    mlp = next((s for s in seats or [] if str(s.get("name", "")).lower() in ("mlp", "main", "main seat")), (seats or [None])[0])
    if mlp and all(mlp.get(k) is not None for k in ("x_m", "y_m")):
        seat = (mlp["x_m"], mlp["y_m"], mlp.get("z_m") if mlp.get("z_m") is not None else 1.0)
        off = []
        for ch, sp in (speakers or {}).items():
            rx = sp.get("rx_distance_m")
            if rx is None or sp.get("x_m") is None or sp.get("y_m") is None:
                continue
            geo = _dist_ft(seat, (sp["x_m"], sp["y_m"], sp.get("z_m") if sp.get("z_m") is not None else seat[2]))
            d = rx / 0.3048 - geo
            if abs(d) > DIST_TOL_FT:
                off.append(f"{ch} {rx / 0.3048:.1f} ft in the receiver vs {geo:.1f} ft measured with a tape ({d:+.1f})")
        if off:
            out.append({"status": "watch", "text": "Receiver distances that don't match where the speakers are: " + "; ".join(off)
                        + ". Small differences are normal after Dirac Live (it sets distances from the acoustic arrival, "
                        "which includes the speaker's own delay); more than about 1 ft usually means a position or a setting is wrong."})
    return out
