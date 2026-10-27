"""Fact-Checker: hard checks in code first, then an AI review.

Anything that fails here never reaches IK Start's owners.
"""
from __future__ import annotations

import json
import re
import unicodedata

from . import llm
from .prompts import FACT_CHECKER, LANG_NAME, prompt_data

NUM_RE = re.compile(r"\d{1,3}(?:[  .,]\d{3})+(?!\d)|\d+")
SCORE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[–\-:]\s*(\d{1,2})(?!\d)")
QUOTE_RE = re.compile(r"[\"“”«»„]([^\"“”«»„]{12,})[\"“”«»„]")
URL_RE = re.compile(r"https?://\S+")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip()


def _nums(text: str) -> set[int]:
    out = set()
    for tok in NUM_RE.findall(text or ""):
        out.add(int(re.sub(r"[  .,]", "", tok)))
    return out


def allowed_numbers(data: dict) -> set[int]:
    """Every number that legitimately appears in DATA."""
    nums: set[int] = set(range(0, 11))  # small counting words ("two games left") are fine
    nums |= _nums(data["today"])
    for team in data["teams"].values():
        for m in team["recent_results"] + team["next_matches"]:
            for k in ("home_goals", "away_goals", "attendance"):
                if m.get(k) is not None:
                    nums.add(int(m[k]))
            nums |= _nums(m["date"]) | _nums(m["kickoff"]) | _nums(str(m["round"]))
            nums |= _nums(" ".join(m["scorers"])) | _nums(m["competition"])
        for row in team["table"]:
            nums |= {row["pos"], row["played"], row["won"], row["drawn"], row["lost"], row["pts"]}
            nums |= _nums(row["gd"])
    for n in data["notes"]:
        nums |= _nums(" ".join(n.get(k, "") for k in ("title", "text", "quote")))
    return nums


def _texts(obj, path=""):
    """Yield (field_path, text) for every string a writer produced."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("match_id", "note_id", "coach_quote_note_id", "missing"):
                continue
            yield from _texts(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _texts(v, f"{path}[{i}]")


def _ids(obj, key):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key and isinstance(v, str):
                yield v
            else:
                yield from _ids(v, key)
    elif isinstance(obj, list):
        for v in obj:
            yield from _ids(v, key)


def hard_checks(data: dict, drafts: dict) -> list[dict]:
    issues = []
    nums_ok = allowed_numbers(data)
    match_ids = {m["match_id"]: m for t in data["teams"].values()
                 for m in t["recent_results"] + t["next_matches"]}
    note_ids = {n["note_id"] for n in data["notes"]}
    quotes = [_norm(n["quote"]) for n in data["notes"] if n.get("quote")]

    for name, draft in drafts.items():
        # 1. Unknown match / note references
        for mid in _ids(draft, "match_id"):
            if mid not in match_ids:
                issues.append({"where": f"{name}", "problem": f"unknown match_id {mid}",
                               "fix": "use a match_id from DATA"})
        for nid in list(_ids(draft, "note_id")) + [draft.get("coach_quote_note_id")]:
            if nid and nid not in note_ids:
                issues.append({"where": f"{name}", "problem": f"unknown note_id {nid}",
                               "fix": "use a note_id from DATA"})
        # 2. Missing facts the writer flagged
        if draft.get("missing"):
            issues.append({"where": f"{name}.missing", "problem": "writer is missing facts: "
                           + "; ".join(draft["missing"]), "fix": "add them to the club sheet"})
        for path, text in _texts(draft):
            where = f"{name}.{path}"
            if "[MANGLER]" in text:
                issues.append({"where": where, "problem": "contains [MANGLER] (missing fact)",
                               "fix": "add the fact to the club sheet"})
            # 3. Numbers not in DATA
            bad = sorted(n for n in _nums(text) if n not in nums_ok)
            if bad:
                issues.append({"where": where, "problem": f"numbers not found in DATA: {bad}",
                               "fix": "only use numbers from DATA"})
            # 4. Links: writers must not type URLs (code adds them)
            for url in URL_RE.findall(text):
                issues.append({"where": where, "problem": f"typed a link {url}",
                               "fix": "remove it; links are added from DATA"})
            # 5. Invented quotes
            for q in QUOTE_RE.findall(text):
                if not any(_norm(q) in src for src in quotes):
                    issues.append({"where": where, "problem": f"quote not found in notes: {q[:60]}",
                                   "fix": "only use quotes from a note's quote field"})
        # 6. Scores in recaps must match the real result
        for item in draft.get("results", []) + draft.get("recaps", []):
            m = match_ids.get(item.get("match_id"))
            if not m or m["home_goals"] is None:
                continue
            real = {(m["home_goals"], m["away_goals"]), (m["away_goals"], m["home_goals"])}
            for field in ("headline", "recap", "text"):
                for a, b in SCORE_RE.findall(item.get(field, "")):
                    if (int(a), int(b)) not in real:
                        issues.append({"where": f"{name}.{item['match_id']}.{field}",
                                       "problem": f"score {a}-{b} does not match the result "
                                                  f"{m['home_goals']}-{m['away_goals']}",
                                       "fix": "use the score from DATA"})
    # 7. Newsletter basics
    nl = drafts.get("newsletter")
    if nl:
        if len(nl.get("subject", "")) > 70:
            issues.append({"where": "newsletter.subject", "problem": "subject longer than 70 characters",
                           "fix": "shorten it"})
        if not nl.get("results") and not nl.get("next_games"):
            issues.append({"where": "newsletter", "problem": "no results and no next games",
                           "fix": "cover the week's matches"})
    return issues


def ai_review(data: dict, drafts: dict, lang: str) -> list[dict]:
    if llm.provider() == "demo":
        return []
    system = FACT_CHECKER.format(language=LANG_NAME[lang])
    user = ("DATA:\n" + json.dumps(prompt_data(data), ensure_ascii=False)
            + "\n\nDRAFTS:\n" + json.dumps(drafts, ensure_ascii=False))
    res = llm.ask_json(system, user)
    return [] if res.get("pass") else res.get("issues", [])


def check(data: dict, drafts: dict, lang: str) -> dict:
    issues = hard_checks(data, drafts)
    if not issues:  # only spend an AI call once the hard checks pass
        issues = ai_review(data, drafts, lang)
    return {"pass": not issues, "issues": issues}
