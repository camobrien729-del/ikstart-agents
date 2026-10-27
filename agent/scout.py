"""Scout: collects the facts. Plain code, no AI.

Reads the club's Google Sheet (tabs: matches, table, notes, settings, approvals)
or local CSV files, cleans them, and returns one DATA dictionary that every
other agent works from.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from datetime import date, datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
TEAMS = ("kvinner", "herrer")
TABS = ("matches", "table", "notes", "settings", "approvals")


class DataError(Exception):
    """Raised when the sheet has a problem a person must fix (bad date, missing team...)."""


def sheet_tab_url(sheet_id: str, tab: str) -> str:
    """CSV of one tab of a Google Sheet shared as 'Anyone with the link: Viewer'."""
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&headers=1&sheet={tab}"


def sheet_id() -> str:
    """The club sheet: GitHub variable SHEET_ID if set, else club.json → sheet_id."""
    if os.environ.get("SHEET_ID", "").strip():
        return os.environ["SHEET_ID"].strip()
    return json.loads((ROOT / "club.json").read_text(encoding="utf-8")).get("sheet_id", "").strip()


def tab_source(tab: str) -> str:
    """Where to read a tab: SHEET_<TAB>_CSV if set, else the shared club sheet."""
    if os.environ.get(f"SHEET_{tab.upper()}_CSV"):
        return os.environ[f"SHEET_{tab.upper()}_CSV"]
    if sheet_id():
        return sheet_tab_url(sheet_id(), tab)
    raise DataError("The club sheet is not connected: put its ID in club.json → sheet_id.")


def _read_csv(source: str) -> list[dict]:
    """Read a CSV from a URL (published Google Sheet tab) or a local path."""
    if source.startswith("http"):
        resp = requests.get(source, timeout=30)
        text = resp.content.decode("utf-8-sig")
        if resp.status_code >= 400 or text.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
            raise DataError("Could not read the club sheet. In Google Sheets: Share → General access → "
                            "'Anyone with the link' → Viewer. (HTTP %s)" % resp.status_code)
    else:
        text = Path(source).read_text(encoding="utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    return [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in rows]


def parse_date(v: str):
    """Accepts 2026-10-24 (preferred), 24.10.2026 (Norwegian) and 10/24/2026 (US Google Sheets)."""
    v = (v or "").strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            pass
    raise ValueError(v)


def parse_time(v: str) -> str:
    v = (v or "").strip().replace(".", ":")
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p"):
        try:
            return datetime.strptime(v, fmt).strftime("%H:%M")
        except ValueError:
            pass
    raise ValueError(v)


def _int_or_none(v: str):
    v = (v or "").strip()
    if v == "":
        return None
    v = v.replace(" ", "").replace("\u00a0", "").replace(",", "")
    if v.endswith(".0"):
        v = v[:-2]
    try:
        return int(v)
    except ValueError:
        raise ValueError(f"Expected a whole number, got {v!r}")


def _clean_matches(rows: list[dict]) -> list[dict]:
    out, problems = [], []
    seen = set()
    for i, r in enumerate(rows, start=2):  # row 1 is the header
        if not any(r.values()):
            continue
        mid = r.get("match_id", "")
        where = f"matches row {i} ({mid or 'no id'})"
        if not mid:
            problems.append(f"{where}: match_id is empty")
            continue
        if mid in seen:
            problems.append(f"{where}: match_id is used twice")
        seen.add(mid)
        team = r.get("team", "").lower()
        if team not in TEAMS:
            problems.append(f"{where}: team must be 'kvinner' or 'herrer'")
        try:
            d = parse_date(r.get("date", ""))
        except ValueError:
            problems.append(f"{where}: date must look like 2026-10-24")
            continue
        ko = r.get("kickoff", "")
        if ko:
            try:
                ko = parse_time(ko)
            except ValueError:
                problems.append(f"{where}: kickoff must look like 13:00")
        status = r.get("status", "").lower() or ("played" if r.get("home_goals") else "upcoming")
        try:
            hg, ag = _int_or_none(r.get("home_goals")), _int_or_none(r.get("away_goals"))
            att = _int_or_none(r.get("attendance"))
        except ValueError as e:
            problems.append(f"{where}: {e}")
            continue
        if status == "played" and (hg is None or ag is None):
            problems.append(f"{where}: played match needs home_goals and away_goals")
        scorers = [s.strip() for s in r.get("scorers", "").split(";") if s.strip()]
        out.append({
            "match_id": mid, "team": team,
            "competition": r.get("competition", ""), "round": r.get("round", ""),
            "date": d.isoformat(), "kickoff": ko,
            "home_team": r.get("home_team", ""), "away_team": r.get("away_team", ""),
            "venue": r.get("venue", ""),
            "home_goals": hg, "away_goals": ag, "scorers": scorers, "attendance": att,
            "ticket_url": r.get("ticket_url", ""), "status": status,
        })
    if problems:
        raise DataError("\n".join(problems))
    return sorted(out, key=lambda m: (m["date"], m["kickoff"]))


def _clean_table(rows: list[dict]) -> dict:
    table = {t: [] for t in TEAMS}
    for i, r in enumerate(rows, start=2):
        if not any(r.values()):
            continue
        t = r.get("team", "").lower()
        if t not in TEAMS:
            raise DataError(f"table row {i}: team must be 'kvinner' or 'herrer' (got {t!r})")
        try:
            nums = {k: _int_or_none(r.get(k, "")) for k in ("pos", "played", "won", "drawn", "lost", "pts")}
        except ValueError as e:
            raise DataError(f"table row {i} ({r.get('club', '')}): {e}")
        if None in nums.values() or not r.get("club"):
            raise DataError(f"table row {i}: fill in pos, club, played, won, drawn, lost and pts")
        gd = r.get("gd", "").strip()
        if gd.lstrip("+-").isdigit() and not gd.startswith(("+", "-")) and gd != "0":
            gd = "+" + gd
        table[t].append(nums | {"club": r["club"], "gd": gd})
    for t in TEAMS:
        table[t].sort(key=lambda x: x["pos"])
    return table


def _clean_notes(rows: list[dict]) -> list[dict]:
    notes = []
    for r in rows:
        if not any(r.values()):
            continue
        team = (r.get("team") or "both").lower()
        if team not in TEAMS + ("both",):
            raise DataError(f"notes {r.get('note_id')}: team must be kvinner, herrer or both")
        notes.append({k: r.get(k, "") for k in
                      ("note_id", "type", "title", "text", "quote", "quote_by", "link", "image_url")}
                     | {"team": team})
    return notes


def read_tab(source: str, tab: str) -> list[dict]:
    """Rows of one tab. source='sample' reads sample_data/<tab>.csv (missing file = empty)."""
    if source == "sample":
        path = ROOT / "sample_data" / f"{tab}.csv"
        return _read_csv(str(path)) if path.exists() else []
    return _read_csv(tab_source(tab))


def read_settings(source: str) -> dict:
    """settings tab: two columns, key and value."""
    out = {}
    for r in read_tab(source, "settings"):
        k = (r.get("key") or "").strip().lower()
        if k:
            out[k] = (r.get("value") or "").strip()
    return out


def owner_emails(settings: dict) -> list[str]:
    raw = settings.get("owner_emails", "") or os.environ.get("OWNER_EMAILS", "")
    return [e.strip() for e in raw.replace(";", ",").replace("\n", ",").split(",") if "@" in e]


def collect(source: str = "sheet", today: date | None = None) -> dict:
    """Build DATA from the club sheet (source='sheet') or sample_data/ (source='sample')."""
    today = today or date.today()
    matches = _clean_matches(read_tab(source, "matches"))
    table = _clean_table(read_tab(source, "table"))
    notes = _clean_notes(read_tab(source, "notes"))
    settings = read_settings(source)
    club = json.loads((ROOT / "club.json").read_text(encoding="utf-8"))
    if settings.get("newsletter_signup_link", "").startswith("http"):
        club["links"]["newsletter_signup"] = settings["newsletter_signup_link"]

    data = {"today": today.isoformat(), "club": club, "teams": {}, "notes": notes}
    for t in TEAMS:
        tm = [m for m in matches if m["team"] == t]
        played = [m for m in tm if m["status"] == "played"]
        upcoming = [m for m in tm if m["status"] != "played" and m["date"] >= today.isoformat()]
        data["teams"][t] = {
            "name": club["teams"][t]["name"],
            "last_result": played[-1] if played else None,
            "recent_results": played[-3:],
            "next_matches": upcoming[:2],
            "table": table[t],
        }
    data["fingerprint"] = fingerprint(data)
    return data


def fingerprint(data: dict) -> str:
    """Hash of the facts, used to skip runs when nothing has changed."""
    core = {k: v for k, v in data.items() if k not in ("today", "fingerprint")}
    return hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def matches_by_id(data: dict) -> dict:
    out = {}
    for t in data["teams"].values():
        for m in t["recent_results"] + t["next_matches"]:
            out[m["match_id"]] = m
    return out
