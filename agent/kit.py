"""Minimal Kit (kit.com) API v4 client: creates scheduled broadcasts.

Kit does the actual sending, unsubscribe links and open/click stats.
Docs: https://developers.kit.com/api-reference/broadcasts/create-a-broadcast
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

import requests

API = "https://api.kit.com/v4"


class KitError(Exception):
    pass


def configured() -> bool:
    return bool(os.environ.get("KIT_API_KEY"))


def _body_only(html: str) -> str:
    """Kit wraps our content in the account's email template, so send only the body."""
    m = re.search(r"<body[^>]*>(.*)</body>", html, re.S | re.I)
    return m.group(1).strip() if m else html


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def create_broadcast(subject: str, preview_text: str, html: str, tag_id: int,
                     send_at: datetime | None, description: str, public: bool = False) -> dict:
    """send_at=None saves a draft in Kit; a datetime schedules the send."""
    key = os.environ.get("KIT_API_KEY")
    if not key:
        raise KitError("KIT_API_KEY is not set")
    body = {
        "subject": subject,
        "preview_text": preview_text,
        "content": _body_only(html),
        "description": description,
        "public": public,
        "published_at": _iso(datetime.now(timezone.utc)),
        "send_at": _iso(send_at) if send_at else None,
        "subscriber_filter": [{"all": None, "any": [{"type": "tag", "ids": [int(tag_id)]}], "none": None}],
    }
    if os.environ.get("KIT_EMAIL_TEMPLATE_ID"):
        body["email_template_id"] = int(os.environ["KIT_EMAIL_TEMPLATE_ID"])
    r = requests.post(f"{API}/broadcasts", json=body,
                      headers={"X-Kit-Api-Key": key, "Content-Type": "application/json"}, timeout=60)
    if r.status_code >= 300:
        raise KitError(f"Kit error {r.status_code}: {r.text[:400]}")
    return r.json().get("broadcast", r.json())


def soon(minutes: int = 3) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def _req(method: str, path: str, body: dict | None = None) -> dict:
    key = os.environ.get("KIT_API_KEY")
    if not key:
        raise KitError("KIT_API_KEY is not set")
    r = requests.request(method, f"{API}{path}", json=body, timeout=60,
                         headers={"X-Kit-Api-Key": key, "Content-Type": "application/json"})
    if r.status_code >= 300:
        raise KitError(f"Kit error {r.status_code} on {path}: {r.text[:400]}")
    return r.json() if r.content else {}


def ensure_tag(name: str) -> int:
    """Kit returns the existing tag if one with this name already exists, so this is safe to repeat."""
    return int(_req("POST", "/tags", {"name": name})["tag"]["id"])


def ensure_tagged(email: str, tag_id: int) -> None:
    """Create the subscriber if needed, then add the tag."""
    _req("POST", "/subscribers", {"email_address": email})
    _req("POST", f"/tags/{int(tag_id)}/subscribers", {"email_address": email})


def setup(owner_emails: list[str]) -> dict:
    """Make sure the two tags exist and the approvers are on the owners tag. Returns the tag IDs."""
    owner_tag = int(os.environ.get("KIT_OWNER_TAG_ID") or ensure_tag("ikstart-owners"))
    fan_tag = int(os.environ.get("KIT_FAN_TAG_ID") or ensure_tag("game-update-fans"))
    for e in owner_emails:
        try:
            ensure_tagged(e, owner_tag)
        except KitError as err:
            print(f"Could not add approver {e} in Kit: {err}")
    return {"owner": owner_tag, "fan": fan_tag}
