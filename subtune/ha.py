"""Home Assistant: htTamer's state and a few switches over a small token-protected REST API.

Home Assistant's own RESTful integrations talk to it (no add-on to install): a sensor block reads
GET /api/ha/state, and rest_commands call POST /api/ha/slot, /api/ha/night and /api/ha/auto_slot.
The page writes the YAML to paste. Every request needs the Home Assistant token (its own token, not the
MCP one), even from this computer; only its SHA-256 hash is kept. Nothing here plays sound: switching a
slot, muting the subs for the night and the automatic slot are all silent. Actions wait for the
use-at-your-own-risk terms like everything else.
"""
from __future__ import annotations

import hmac
import json
import secrets
import time

FILE = "homeassistant.json"


def _cfg():
    from .config import config_dir
    return config_dir()


def token_info() -> dict:
    try:
        d = json.loads((_cfg() / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    return {"has_token": bool(d.get("token_sha256")), "created": d.get("created")}


def new_token() -> str:
    from .mcp import _sha, _write_private
    tok = "hta_" + secrets.token_urlsafe(32)
    _write_private(_cfg() / FILE, json.dumps({"token_sha256": _sha(tok), "created": time.time()}))
    return tok


def revoke_token() -> None:
    try:
        (_cfg() / FILE).unlink()
    except FileNotFoundError:
        pass


def bearer_ok(header: str | None) -> bool:
    from .mcp import _sha
    if not header or not header.lower().startswith("bearer "):
        return False
    got = header[7:].strip()
    try:
        d = json.loads((_cfg() / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(got) and bool(d.get("token_sha256")) and hmac.compare_digest(_sha(got), d["token_sha256"])


def state(dsp_status=None, avr=None, busy=False) -> dict:
    """What Home Assistant shows. dsp_status: the miniDSP's master block if known."""
    from . import automation, library, version
    m = dsp_status or {}
    slot = int(m["preset"]) + 1 if m.get("preset") is not None else None
    names = {}
    try:
        names = {int(k): (v or {}).get("name") for k, v in (library.slots() or {}).items()}
    except Exception:                                  # noqa: BLE001
        pass
    if slot == 1:
        names.setdefault(1, "your original setup")
    a = avr or {}
    return {"slot": slot, "tune": names.get(slot) if slot else None, "night": automation.night_on(),
            "auto_slot": bool(automation.status()["auto_slot_on"]), "busy": bool(busy),
            "receiver_on": bool(a.get("power")), "input": a.get("input"), "mode": a.get("mode"),
            "sub_level": a.get("sub_level"), "version": version()}


def yaml(base_url: str) -> str:
    """The configuration to paste into Home Assistant (configuration.yaml), plus the secret to add."""
    u = base_url.rstrip("/")
    return f"""# --- secrets.yaml: put your token after "Bearer " (Tools -> Home Assistant -> Make a token)
# httamer_auth: "Bearer hta_..."

# --- configuration.yaml
rest:
  - resource: {u}/api/ha/state
    headers:
      Authorization: !secret httamer_auth
    scan_interval: 15
    sensor:
      - name: htTamer slot
        unique_id: httamer_slot
        value_template: "{{{{ value_json.slot }}}}"
      - name: htTamer tune
        unique_id: httamer_tune
        value_template: "{{{{ value_json.tune }}}}"
      - name: htTamer receiver sub level
        unique_id: httamer_sub_level
        unit_of_measurement: dB
        value_template: "{{{{ value_json.sub_level }}}}"
    binary_sensor:
      - name: htTamer night mode
        unique_id: httamer_night
        value_template: "{{{{ value_json.night }}}}"
      - name: htTamer automatic slot
        unique_id: httamer_auto_slot
        value_template: "{{{{ value_json.auto_slot }}}}"

rest_command:
  httamer_slot:        # data: slot: 1-4
    url: {u}/api/ha/slot
    method: POST
    headers:
      Authorization: !secret httamer_auth
    content_type: application/json
    payload: '{{"slot": {{{{ slot }}}}}}'
  httamer_night:       # data: on: true / false
    url: {u}/api/ha/night
    method: POST
    headers:
      Authorization: !secret httamer_auth
    content_type: application/json
    payload: '{{"on": {{{{ on | lower }}}}}}'
  httamer_auto_slot:   # data: on: true / false
    url: {u}/api/ha/auto_slot
    method: POST
    headers:
      Authorization: !secret httamer_auth
    content_type: application/json
    payload: '{{"on": {{{{ on | lower }}}}}}'

# --- example: a "movie night" script
# script:
#   httamer_movie_night:
#     sequence:
#       - action: rest_command.httamer_slot
#         data: {{slot: 3}}
#       - action: rest_command.httamer_night
#         data: {{on: false}}
"""
