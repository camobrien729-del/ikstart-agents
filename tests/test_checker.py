"""Run with:  python -m pytest -q   (or  python tests/test_checker.py)"""
import copy
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["LLM_PROVIDER"] = "demo"

from agent import checker, scout, writers  # noqa: E402

DATA = scout.collect("sample", date(2026, 10, 5))


def drafts():
    return {"newsletter": writers.write_newsletter(DATA, "en"),
            "website": writers.write_website(DATA, "en")}


def problems(d):
    return [i["problem"] for i in checker.hard_checks(DATA, d)]


def test_clean_draft_passes():
    assert checker.check(DATA, drafts(), "en")["pass"]


def test_wrong_score_is_caught():
    d = drafts()
    d["newsletter"]["results"][0]["recap"] = "Start Kvinner won 3-0 against Tromsø."
    assert any("does not match the result" in p for p in problems(d))


def test_invented_number_is_caught():
    d = drafts()
    d["newsletter"]["intro"] = "A record 4512 fans came to watch."
    assert any("4512" in p for p in problems(d))


def test_invented_quote_is_caught():
    d = drafts()
    d["newsletter"]["intro"] = 'The coach said "this was the best game we have ever played".'
    assert any("quote not found" in p for p in problems(d))


def test_real_quote_is_allowed():
    d = drafts()
    d["newsletter"]["intro"] = 'As the coach says, "We always focus on one game at a time, and on developing continuously."'
    assert not any("quote" in p for p in problems(d))


def test_typed_link_is_caught():
    d = drafts()
    d["website"]["recaps"][0]["text"] += " Tickets at https://example.com"
    assert any("typed a link" in p for p in problems(d))


def test_unknown_match_is_caught():
    d = drafts()
    d["newsletter"]["next_games"].append({"match_id": "FAKE-1", "hook": "Come along."})
    assert any("unknown match_id" in p for p in problems(d))


def test_missing_fact_blocks():
    d = drafts()
    d["newsletter"]["intro"] = "Kickoff is at [MANGLER]."
    assert any("MANGLER" in p for p in problems(d))


def test_bad_sheet_row_is_reported(tmp_path=None):
    bad = scout._clean_matches  # date in the wrong format must raise a DataError
    try:
        bad([{"match_id": "X", "team": "kvinner", "date": "24/10/2026", "home_team": "A", "away_team": "B"}])
    except scout.DataError as e:
        assert "date must look like" in str(e)
    else:
        raise AssertionError("bad date was not reported")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok  ", name)
