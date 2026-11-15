"""Use-at-your-own-risk terms the owner accepts once per device before htTamer can act.

htTamer plays loud test sound, changes the receiver's volume and input, and writes the miniDSP.
Until the current TERMS_VERSION is accepted, the dashboard refuses actions (server.do_POST) and
the page shows the terms. Raising TERMS_VERSION asks everyone again. The acceptance is stored in
the settings file (kept across updates), with the time and where it was accepted from.
"""
from __future__ import annotations

import time

TERMS_VERSION = 1

TITLE = "Before you start: use at your own risk"
POINTS = [
    "htTamer plays test tones, sweeps and noise through your receiver, speakers and subwoofers, changes "
    "the receiver's volume and input, and writes settings to your miniDSP.",
    "Loud sound, low bass especially, can damage speakers, subwoofers, amplifiers and hearing. Start with "
    "the volume low, keep people and pets out of the room for loud tests, and press Stop at the first sign "
    "of strain (distortion, rattling, a smell of heat).",
    "Results are calculated from measurements and can be wrong. Check every change by ear before relying "
    "on it. htTamer never writes miniDSP slot 1, so your original setup stays there.",
    "htTamer is provided \"as is\", without warranty of any kind, under the PolyForm Noncommercial License "
    "1.0.0. You use it entirely at your own risk: the htTamer authors are not liable for damage to "
    "equipment, property or hearing, or for any other loss, however it is caused.",
    "htTamer isn't made, endorsed or supported by Onkyo, Denon, Marantz, JBL, miniDSP, Dirac or any other "
    "company whose products it works with.",
]
CHECKBOX = "I've read this, I understand the risks, and I use htTamer at my own risk."


def status(s=None) -> dict:
    from .config import load_settings
    a = (s or load_settings()).get("terms_accepted") or {}
    ok = isinstance(a, dict) and a.get("v") == TERMS_VERSION
    return {"accepted": ok, "version": TERMS_VERSION, "t": a.get("t") if ok else None,
            "title": TITLE, "points": POINTS, "checkbox": CHECKBOX}


def accepted(s=None) -> bool:
    return status(s)["accepted"]


def accept(where: str = "") -> dict:
    from .config import load_settings, save_settings
    from .state import event
    s = load_settings()
    s["terms_accepted"] = {"v": TERMS_VERSION, "t": time.time()}
    save_settings(s)
    event("config", f"use-at-your-own-risk terms (version {TERMS_VERSION}) accepted" + (f" from {where}" if where else ""))
    return status(s)


# POSTs allowed before the terms are accepted: reading/accepting them, signing in, error reports
OPEN_PATHS = {"/api/terms", "/api/login", "/api/logout", "/api/setup/pin", "/api/setup/done", "/api/client-error"}
