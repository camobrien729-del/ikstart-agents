"""End-to-end test of the weekly flow on sample data (no AI, nothing sent).

Runs in a temporary copy of the project so the real state is never touched.
Run with:  python tests/test_flow.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(tmp: Path, now: str, *args):
    env = os.environ | {"LLM_PROVIDER": "demo", "AGENT_NOW": now, "AGENT_TODAY": now[:10],
                        "SITE_URL": "https://example.github.io/ikstart-agents"}
    env.pop("KIT_API_KEY", None)
    env.pop("GITHUB_OUTPUT", None)
    env.pop("GITHUB_STEP_SUMMARY", None)
    r = subprocess.run([sys.executable, "-m", "agent.run", "tick", "--source", "sample", "--no-send", *args],
                       cwd=tmp, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def approvals(tmp: Path, rows):
    lines = ["code,decision,feedback,name"] + [",".join(r) for r in rows]
    (tmp / "sample_data" / "approvals.csv").write_text("\n".join(lines) + "\n")


def pending(tmp: Path):
    p = tmp / "pending" / "pending.json"
    return json.loads(p.read_text()) if p.exists() else None


def test_weekly_flow():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / "proj"
        shutil.copytree(ROOT, tmp, ignore=shutil.ignore_patterns("out", "pending", "__pycache__", ".git"))
        (tmp / "state" / "state.json").write_text(json.dumps({"issue_number": 0}))
        approvals(tmp, [])

        # Monday 2026-10-05, before 07:00: nothing happens
        assert "Nothing to do" in run(tmp, "2026-10-05T06:30")
        assert pending(tmp) is None

        # 07:10: newsletter day -> draft GU1 is waiting
        run(tmp, "2026-10-05T07:10")
        p = pending(tmp)
        assert p["code"] == "GU1" and p["plan"] == {"newsletter": True, "website": True}

        # 07:40: nobody answered yet -> still waiting, no new draft
        run(tmp, "2026-10-05T07:40")
        assert pending(tmp)["code"] == "GU1"

        # An owner asks for changes -> rewritten as GU1B with the feedback
        approvals(tmp, [("GU1", "ENDRE", "Lead with the attendance", "Kari")])
        out = run(tmp, "2026-10-05T08:10")
        assert "asked for changes" in out
        p = pending(tmp)
        assert p["code"] == "GU1B" and p["feedback"] == "Lead with the attendance"

        # Old code approved by mistake -> ignored; new code approved -> published
        approvals(tmp, [("GU1", "ENDRE", "Lead with the attendance", "Kari"), ("gu-1b", "ja", "", "Ola")])
        out = run(tmp, "2026-10-05T08:40")
        assert "approved by Ola" in out
        assert pending(tmp) is None
        state = json.loads((tmp / "state" / "state.json").read_text())
        assert state["issue_number"] == 1 and state["last_newsletter"] == "2026-10-05"
        feed = json.loads((tmp / "docs" / "data" / "site.json").read_text())
        assert feed["teams"]["kvinner"]["recent_results"]

        # 19:00 the same day: nothing changed -> no new draft, no second newsletter
        assert "No news" in run(tmp, "2026-10-05T19:05")
        assert pending(tmp) is None

        # Tuesday: a new result in the sheet -> website-only draft WEB0610
        m = (tmp / "sample_data" / "matches.csv").read_text().replace(",773,", ",774,")
        (tmp / "sample_data" / "matches.csv").write_text(m)
        run(tmp, "2026-10-06T07:05")
        p = pending(tmp)
        assert p["code"] == "WEB0610" and p["plan"] == {"newsletter": False, "website": True}

        # NEI throws it away
        approvals(tmp, [("WEB0610", "NEI", "", "Ola")])
        assert "rejected" in run(tmp, "2026-10-06T07:35")
        assert pending(tmp) is None


if __name__ == "__main__":
    test_weekly_flow()
    print("ok   test_weekly_flow")
