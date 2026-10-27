"""Web Writer and Newsletter Writer agents."""
from __future__ import annotations

import json
from datetime import date

from . import llm
from .prompts import LANG_NAME, NEWSLETTER_WRITER, WEB_WRITER, prompt_data
from .scout import matches_by_id


def _user_message(data: dict, feedback: str = "", issues: list | None = None) -> str:
    msg = "DATA:\n" + json.dumps(prompt_data(data), ensure_ascii=False, indent=1)
    if feedback:
        msg += "\n\nCHANGES REQUESTED BY IK START (follow these):\n" + feedback
    if issues:
        msg += "\n\nYOUR LAST DRAFT FAILED THESE CHECKS. Fix every one:\n" + json.dumps(issues, ensure_ascii=False, indent=1)
    return msg


def write_newsletter(data: dict, lang: str, feedback: str = "", issues=None) -> dict:
    if llm.provider() == "demo":
        return _demo_newsletter(data, lang)
    system = NEWSLETTER_WRITER.format(language=LANG_NAME[lang])
    return llm.ask_json(system, _user_message(data, feedback, issues))


def write_website(data: dict, lang: str, feedback: str = "", issues=None) -> dict:
    if llm.provider() == "demo":
        return _demo_website(data, lang)
    system = WEB_WRITER.format(language=LANG_NAME[lang])
    return llm.ask_json(system, _user_message(data, feedback, issues))


# ---------------------------------------------------------------------------
# Demo writers: no AI, built only from DATA. Used for tests and offline demos.
# ---------------------------------------------------------------------------
T = {
    "en": {"beat": "beat", "drew": "drew with", "lost": "lost to", "goals": "Goals",
           "fans": "fans", "next": "Next up", "come": "Come and back the team"},
    "nb": {"beat": "slo", "drew": "spilte uavgjort mot", "lost": "tapte mot", "goals": "Mål",
           "fans": "tilskuere", "next": "Neste", "come": "Kom og støtt laget"},
}


def _result_line(m: dict, team_name: str, lang: str) -> tuple[str, str]:
    t = T[lang]
    home = m["home_team"] == team_name or m["home_team"].startswith(team_name.split()[0])
    us, them = (m["home_goals"], m["away_goals"]) if home else (m["away_goals"], m["home_goals"])
    opp = m["away_team"] if home else m["home_team"]
    verb = t["beat"] if us > them else (t["drew"] if us == them else t["lost"])
    headline = f"{team_name} {verb} {opp} {us}–{them}"
    parts = [f"{team_name} {verb} {opp} {us}–{them} at {m['venue']}." if lang == "en"
             else f"{team_name} {verb} {opp} {us}–{them} på {m['venue']}."]
    if m["scorers"]:
        parts.append(f"{t['goals']}: {', '.join(m['scorers'])}.")
    if m["attendance"]:
        parts.append(f"{m['attendance']} {t['fans']}." )
    return headline, " ".join(parts)


def _note(data, ntype):
    return next((n for n in data["notes"] if n["type"] == ntype), None)


def _demo_newsletter(data: dict, lang: str) -> dict:
    results, nexts = [], []
    for key, team in data["teams"].items():
        if team["last_result"]:
            h, r = _result_line(team["last_result"], team["name"], lang)
            results.append({"match_id": team["last_result"]["match_id"], "headline": h, "recap": r})
        for m in team["next_matches"]:
            nexts.append({"match_id": m["match_id"], "hook": T[lang]["come"] + "."})
    sp, cq, gv, ev, pa, vo = (_note(data, x) for x in
                              ("player_spotlight", "coach_quote", "giveaway", "event", "partner", "volunteer"))
    lead = results[0]["headline"] if results else "The Game Update"
    return {
        "subject": lead[:60], "preview_text": "Results, the table and the next games for both teams.",
        "headline": lead[:50],
        "intro": "Here is the week at IK Start: results, the table and the next games for both teams.",
        "results": results,
        "table_notes": {k: "" for k in data["teams"]},
        "player_spotlight": {"note_id": sp["note_id"], "text": sp["text"]} if sp else None,
        "coach_quote_note_id": cq["note_id"] if cq else None,
        "next_games": nexts,
        "giveaway": {"note_id": gv["note_id"], "text": gv["text"]} if gv else None,
        "event": {"note_id": ev["note_id"], "text": ev["text"]} if ev else None,
        "partner": {"note_id": pa["note_id"], "text": pa["text"]} if pa else None,
        "volunteer": {"note_id": vo["note_id"], "text": vo["text"]} if vo else None,
        "missing": [],
    }


def _demo_website(data: dict, lang: str) -> dict:
    recaps, previews, news = [], [], []
    home_next = []
    for team in data["teams"].values():
        if team["last_result"]:
            h, r = _result_line(team["last_result"], team["name"], lang)
            recaps.append({"match_id": team["last_result"]["match_id"], "headline": h, "text": r})
        for m in team["next_matches"]:
            previews.append({"match_id": m["match_id"],
                             "headline": f"{m['home_team']} – {m['away_team']}",
                             "text": T[lang]["come"] + "."})
            if m["home_team"].startswith(team["name"].split()[0]) or m["home_team"] == team["name"]:
                home_next.append(m)
    for n in data["notes"]:
        if n["type"] in ("news", "event", "player_spotlight"):
            news.append({"note_id": n["note_id"], "headline": n["title"], "text": n["text"]})
    home_next.sort(key=lambda m: (m["date"], m["kickoff"]))
    hp = {"match_id": home_next[0]["match_id"], "hook": T[lang]["come"] + "."} if home_next else None
    return {"homepage": hp, "recaps": recaps, "previews": previews, "news": news, "missing": []}
