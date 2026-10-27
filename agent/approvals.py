"""Reads IK Start's decisions from the 'approvals' tab of the club sheet.

Each draft gets a short code (e.g. GU12 or WEB2710). To answer, an owner adds a row:

    code   | decision | feedback                         | name
    GU12   | JA       |                                  | Ola
    GU12   | ENDRE    | Start with the women's result    | Kari

JA publishes, ENDRE sends the draft back to the writers with the feedback,
NEI throws the draft away. Only people with edit access to the sheet can answer.
"""
from __future__ import annotations

import re

APPROVE = {"ja", "yes", "y", "ok", "godkjent", "godkjenn", "godkjenner", "approve", "approved", "send"}
CHANGES = {"endre", "endring", "endringer", "change", "changes", "fix", "rett"}
STOP = {"nei", "no", "n", "stopp", "stop", "avbryt", "cancel", "slett"}


def norm_code(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def decision_for(rows: list[dict], code: str) -> dict | None:
    """The latest answer for this draft code, or None if nobody has answered yet."""
    want = norm_code(code)
    for r in reversed(rows):
        if norm_code(r.get("code", "")) != want:
            continue
        d = norm_code(r.get("decision", ""))
        fb = (r.get("feedback") or "").strip()
        who = (r.get("name") or "").strip()
        if d in APPROVE:
            return {"decision": "approve", "feedback": fb, "by": who}
        if d in STOP:
            return {"decision": "stop", "feedback": fb, "by": who}
        if d in CHANGES or fb:
            return {"decision": "changes", "feedback": fb, "by": who}
    return None


def next_revision(code: str) -> str:
    """GU12 -> GU12B -> GU12C ..."""
    m = re.match(r"^(.*?\d+)([A-Z]?)$", code)
    if not m:
        return code + "B"
    base, letter = m.groups()
    return base + (chr(ord(letter) + 1) if letter else "B")
