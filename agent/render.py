"""Turns approved writing + DATA facts into the finished newsletter email and the website feed.

The writers never type facts: scores, dates, kickoff times, venues, tables and ticket
links all come straight from DATA here, so the layout and the facts are always right.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .scout import matches_by_id

ROOT = Path(__file__).resolve().parent.parent

LABELS = {
    "en": {"results": "Results", "table": "League table", "spotlight": "Player spotlight",
           "coach": "From the coach", "next": "Next games", "tickets": "Buy tickets",
           "giveaway": "Win with the Game Update", "event": "Don't miss", "partner": "Partner news",
           "volunteer": "Get involved", "goals": "Goals", "fans": "fans", "home": "Home", "away": "Away",
           "issue": "Issue", "kickoff": "Kickoff", "read_more": "Read more", "website": "Website",
           "pos": "#", "club": "Team", "p": "P", "pts": "Pts", "gd": "GD",
           "months": ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"],
           "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
           "footer": "You get the Game Update because you bought a ticket or signed up on our website."},
    "nb": {"results": "Resultater", "table": "Tabellen", "spotlight": "Ukens spiller",
           "coach": "Fra treneren", "next": "Neste kamper", "tickets": "Kjøp billetter",
           "giveaway": "Vinn med Game Update", "event": "Ikke gå glipp av", "partner": "Fra partnerne",
           "volunteer": "Bli med", "goals": "Mål", "fans": "tilskuere", "home": "Hjemme", "away": "Borte",
           "issue": "Utgave", "kickoff": "Avspark", "read_more": "Les mer", "website": "Nettside",
           "pos": "#", "club": "Lag", "p": "K", "pts": "P", "gd": "MF",
           "months": ["JAN", "FEB", "MAR", "APR", "MAI", "JUN", "JUL", "AUG", "SEP", "OKT", "NOV", "DES"],
           "days": ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"],
           "footer": "Du får Game Update fordi du har kjøpt billett eller meldt deg på via nettsiden."},
}


APPROVE_TEXT = {
    "nb": {"kicker": "FORHÅNDSVISNING FOR IK START · IKKE SENDT TIL FANS ENNÅ",
           "intro": "Slik ser e-posten ut for fansen. Ingenting publiseres før dere godkjenner.",
           "how": "Slik svarer du: åpne klubbarket → fanen <b>approvals</b> → legg til en rad:",
           "yes": "publiser nettsiden og send nyhetsbrevet",
           "change": "skriv hva som skal endres i <i>feedback</i>, så kommer et nytt utkast",
           "no": "forkast utkastet",
           "button": "Åpne klubbarket", "site": "Endringer på nettsiden:",
           "web_title": "Ny oppdatering av nettsiden venter", "time": "Agentene sjekker arket hver halvtime."},
    "en": {"kicker": "PREVIEW FOR IK START · NOT SENT TO FANS YET",
           "intro": "This is exactly what fans will receive. Nothing is published until you approve.",
           "how": "How to answer: open the club sheet → tab <b>approvals</b> → add a row:",
           "yes": "publish the website and send the newsletter",
           "change": "write what to change under <i>feedback</i> and a new draft arrives",
           "no": "throw the draft away",
           "button": "Open the club sheet", "site": "Website changes:",
           "web_title": "A website update is waiting", "time": "The agents check the sheet every 30 minutes."},
}


def _env() -> Environment:
    return Environment(loader=FileSystemLoader(str(ROOT / "templates")),
                       autoescape=select_autoescape(["html", "j2"]), trim_blocks=True, lstrip_blocks=True)


def _match_view(m: dict, data: dict, L: dict, lang: str) -> dict:
    d = date.fromisoformat(m["date"])
    team = data["teams"][m["team"]]
    is_home = m["home_team"] == team["name"]
    return m | {
        "day": d.day, "month": L["months"][d.month - 1], "weekday": L["days"][d.weekday()],
        "team_label": data["club"]["teams"][m["team"]]["label_" + lang],
        "is_home": is_home,
    }


def build_newsletter(data: dict, nl: dict, lang: str, issue_no: int,
                     preview_for_owners: bool = False, approve: dict | None = None,
                     site_changes: list[str] | None = None) -> str:
    L = LABELS[lang]
    mid = matches_by_id(data)
    notes = {n["note_id"]: n for n in data["notes"]}

    def note_block(key):
        item = nl.get(key)
        if not item or item.get("note_id") not in notes:
            return None
        n = notes[item["note_id"]]
        return {"title": n["title"], "text": item["text"], "link": n.get("link", ""),
                "image_url": n.get("image_url", "")}

    results = [r | {"m": _match_view(mid[r["match_id"]], data, L, lang)} for r in nl.get("results", []) if r["match_id"] in mid]
    next_games = [g | {"m": _match_view(mid[g["match_id"]], data, L, lang)} for g in nl.get("next_games", []) if g["match_id"] in mid]
    next_games.sort(key=lambda g: (g["m"]["date"], g["m"]["kickoff"]))
    tables = []
    for key, team in data["teams"].items():
        if team["table"]:
            tables.append({"label": data["club"]["teams"][key]["label_" + lang],
                           "name": team["name"], "rows": team["table"][:6],
                           "note": (nl.get("table_notes") or {}).get(key, "")})
    cq = notes.get(nl.get("coach_quote_note_id") or "")
    return _env().get_template("newsletter.html.j2").render(
        L=L, club=data["club"], nl=nl, results=results, next_games=next_games, tables=tables,
        spotlight=note_block("player_spotlight"), coach=cq, giveaway=note_block("giveaway"),
        event=note_block("event"), partner=note_block("partner"), volunteer=note_block("volunteer"),
        issue_no=issue_no, today=date.fromisoformat(data["today"]),
        preview=preview_for_owners, approve=approve or {}, A=APPROVE_TEXT[lang], site_changes=site_changes or [],
        site_url=data["club"]["site_url"].rstrip("/"),
    )


def build_website_preview(club: dict, changes: list[str], approve: dict) -> str:
    """Short approval email for website-only updates."""
    lang = club.get("language", "nb")
    return _env().get_template("website_preview.html.j2").render(
        club=club, changes=changes, approve=approve, A=APPROVE_TEXT[lang], site_url=club["site_url"].rstrip("/"))


def build_site_feed(data: dict, web: dict, lang: str) -> dict:
    """The JSON feed the website reads (docs/data/site.json)."""
    mid = matches_by_id(data)
    notes = {n["note_id"]: n for n in data["notes"]}
    text = {r["match_id"]: r for r in web.get("recaps", []) + web.get("previews", [])}
    feed = {"updated": datetime.now().isoformat(timespec="minutes"), "language": lang,
            "homepage": None, "teams": {}, "news": [], "links": data["club"]["links"]}
    hp = web.get("homepage")
    if hp and hp.get("match_id") in mid:
        feed["homepage"] = mid[hp["match_id"]] | {"hook": hp["hook"]}
    for key, team in data["teams"].items():
        feed["teams"][key] = {
            "name": team["name"],
            "label": data["club"]["teams"][key]["label_" + lang],
            "recent_results": [m | {k: text.get(m["match_id"], {}).get(k, "") for k in ("headline", "text")}
                               for m in reversed(team["recent_results"])],
            "next_matches": [m | {k: text.get(m["match_id"], {}).get(k, "") for k in ("headline", "text")}
                             for m in team["next_matches"]],
            "table": team["table"],
        }
    for item in web.get("news", []):
        n = notes.get(item.get("note_id"))
        if n:
            feed["news"].append({"team": n["team"], "headline": item["headline"], "text": item["text"],
                                 "link": n.get("link", ""), "image_url": n.get("image_url", "")})
    return feed


def site_change_summary(old: dict | None, new: dict) -> list[str]:
    """Plain-language list of what changes on the website (shown in the owners' preview)."""
    out = []
    if new.get("homepage") and (not old or (old.get("homepage") or {}).get("match_id") != new["homepage"]["match_id"]):
        h = new["homepage"]
        out.append(f"Homepage now leads with {h['home_team']} – {h['away_team']} ({h['date']} {h['kickoff']})")
    for key, t in new["teams"].items():
        old_t = (old or {}).get("teams", {}).get(key, {})
        old_ids = {m["match_id"] for m in old_t.get("recent_results", [])}
        for m in t["recent_results"]:
            if m["match_id"] not in old_ids and m.get("headline"):
                out.append(f"New match report ({t['label']}): {m['headline']}")
        old_next = {m["match_id"] for m in old_t.get("next_matches", [])}
        for m in t["next_matches"]:
            if m["match_id"] not in old_next and m.get("headline"):
                out.append(f"New preview ({t['label']}): {m['headline']}")
        if old_t.get("table") != t["table"]:
            out.append(f"League table updated ({t['label']})")
    old_news = {n["headline"] for n in (old or {}).get("news", [])}
    for n in new["news"]:
        if n["headline"] not in old_news:
            out.append(f"News: {n['headline']}")
    return out
