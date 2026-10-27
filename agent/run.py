"""Command line entry point for the IK Start agents.

  python -m agent.run tick                  # what GitHub runs every 30 minutes
  python -m agent.run draft [--mode auto|newsletter|website] [--feedback "..."]
  python -m agent.run demo                  # offline demo on sample data: no AI, nothing sent

How a week works:
  * At 07:00 and 19:00 (Norway) the agents look at the club sheet. If anything changed, or it is
    newsletter day, they draft an update and email a preview to IK Start's approvers.
  * The approvers answer in the sheet's 'approvals' tab: JA, ENDRE (+ feedback) or NEI.
  * Every 30 minutes the agents check for an answer. JA publishes the website and schedules the
    newsletter; ENDRE sends the draft back to the writers with the feedback.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import approvals, checker, kit, llm, render, scout, writers

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
PENDING = ROOT / "pending"
STATE = ROOT / "state" / "state.json"
SITE_FEED = ROOT / "docs" / "data" / "site.json"
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MAX_ATTEMPTS = 3
PENDING_DAYS = 7
DRAFT_FILES = ("drafts.json", "data.json", "site.json", "newsletter.html", "newsletter_preview.html", "report.md")


# ---------- small helpers ----------

def club() -> dict:
    return json.loads((ROOT / "club.json").read_text(encoding="utf-8"))


def now_local() -> datetime:
    if os.environ.get("AGENT_NOW"):
        return datetime.fromisoformat(os.environ["AGENT_NOW"]).replace(tzinfo=ZoneInfo(club()["timezone"]))
    return datetime.now(ZoneInfo(club()["timezone"]))


def today_local() -> date:
    if os.environ.get("AGENT_TODAY"):
        return date.fromisoformat(os.environ["AGENT_TODAY"])
    return now_local().date()


def load_state() -> dict:
    s = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    return {"issue_number": 0, "website_fingerprint": None, "last_newsletter": None,
            "newsletter_drafted_on": None, "last_slot": None, "history": []} | s


def save_state(s: dict) -> None:
    s["history"] = s.get("history", [])[-30:]
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")


def load_pending() -> dict | None:
    p = PENDING / "pending.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def clear_pending() -> None:
    if PENDING.exists():
        shutil.rmtree(PENDING)


def site_url(c: dict) -> str:
    if os.environ.get("SITE_URL"):
        return os.environ["SITE_URL"].rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo:  # GitHub Pages address, e.g. https://ikstart.github.io/ikstart-agents
        owner, name = repo.split("/", 1)
        return f"https://{owner.lower()}.github.io/{name}"
    return c.get("site_url", "").rstrip("/")


def sheet_link() -> str:
    sid = scout.sheet_id()
    return f"https://docs.google.com/spreadsheets/d/{sid}/edit" if sid else ""


def _gh_output(**kv):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")


def _gh_summary(text: str):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def log(text: str):
    print(text)
    _gh_summary(text)


# ---------- drafting ----------

def _write_and_check(data, lang, plan, feedback):
    """Writers draft, Fact-Checker checks; failed drafts go back to the writers (max 3 tries)."""
    issues, drafts, result, attempt = None, {}, None, 0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        drafts = {}
        if plan["newsletter"]:
            drafts["newsletter"] = writers.write_newsletter(data, lang, feedback, issues)
        if plan["website"]:
            drafts["website"] = writers.write_website(data, lang, feedback, issues)
        result = checker.check(data, drafts, lang)
        print(f"Attempt {attempt}: {'PASS' if result['pass'] else str(len(result['issues'])) + ' issue(s)'}")
        if result["pass"]:
            break
        issues = result["issues"]
    return drafts, result, attempt


def make_plan(mode: str, data: dict, state: dict, today: date, c: dict) -> dict:
    is_send_day = WEEKDAYS[today.weekday()] == c["newsletter"]["send_weekday"]
    newsletter = mode == "newsletter" or (
        mode == "auto" and is_send_day and state.get("newsletter_drafted_on") != today.isoformat()
        and state.get("last_newsletter") != today.isoformat())
    website = mode in ("website", "newsletter") or newsletter or (
        mode == "auto" and data["fingerprint"] != state.get("website_fingerprint"))
    return {"newsletter": newsletter, "website": website}


def draft(source: str, plan: dict, feedback: str = "", code: str | None = None,
          send: bool = True, data: dict | None = None) -> int:
    """Draft, fact-check, save to pending/ and email the preview. Returns 0 ok, 2 failed checks."""
    OUT.mkdir(exist_ok=True)
    for f in OUT.iterdir():
        f.unlink()
    c = club()
    today = today_local()
    data = data or scout.collect(source, today)
    data["club"]["site_url"] = site_url(c)
    lang = os.environ.get("NEWSLETTER_LANGUAGE") or c.get("language", "nb")
    state = load_state()
    settings = scout.read_settings(source)

    drafts, result, attempts = _write_and_check(data, lang, plan, feedback)
    (OUT / "drafts.json").write_text(json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    issue = state["issue_number"] + 1
    code = code or (f"GU{issue}" if plan["newsletter"] else f"WEB{today:%d%m}")
    report = [f"## Draft {code} · {today.isoformat()}",
              f"- Newsletter: {'yes' if plan['newsletter'] else 'no'}",
              f"- Website update: {'yes' if plan['website'] else 'no'}",
              f"- Fact-check: {'PASSED' if result['pass'] else 'FAILED'} after {attempts} attempt(s)"]
    if feedback:
        report.append(f"- Written with IK Start's feedback: {feedback}")
    if not result["pass"]:
        report += ["", "### Problems to fix (nothing was sent)"] + \
                  [f"- **{i.get('where')}**: {i.get('problem')} → {i.get('fix')}" for i in result["issues"]]
        log("\n".join(report))
        return 2

    changes = []
    if plan["website"]:
        feed = render.build_site_feed(data, drafts["website"], lang)
        old = json.loads(SITE_FEED.read_text(encoding="utf-8")) if SITE_FEED.exists() else None
        changes = render.site_change_summary(old, feed) or ["Small updates to match texts and dates"]
        (OUT / "site.json").write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8")
        report += ["", "### Website changes"] + [f"- {x}" for x in changes]

    approve = {"code": code, "sheet_url": sheet_link()}
    preview_html = None
    if plan["newsletter"]:
        nl = drafts["newsletter"]
        (OUT / "newsletter.html").write_text(render.build_newsletter(data, nl, lang, issue), encoding="utf-8")
        preview_html = render.build_newsletter(data, nl, lang, issue, preview_for_owners=True,
                                               approve=approve, site_changes=changes)
        (OUT / "newsletter_preview.html").write_text(preview_html, encoding="utf-8")
        report += ["", f"### Newsletter #{issue}", f"**Subject:** {nl['subject']}",
                   f"**Preview line:** {nl['preview_text']}"]
        subject = f"[GODKJENN {code}] {nl['subject']}"
    else:
        preview_html = render.build_website_preview(data["club"], changes, approve)
        (OUT / "newsletter_preview.html").write_text(preview_html, encoding="utf-8")
        subject = f"[GODKJENN {code}] Nettsiden: {len(changes)} endring(er)"

    clear_pending()
    PENDING.mkdir()
    for f in DRAFT_FILES:
        if (OUT / f).exists():
            shutil.copy(OUT / f, PENDING / f)
    (PENDING / "pending.json").write_text(json.dumps({
        "code": code, "created": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "plan": plan, "fingerprint": data["fingerprint"], "feedback": feedback,
        "issue": issue if plan["newsletter"] else None, "date": today.isoformat()}, indent=2), encoding="utf-8")
    if plan["newsletter"]:
        state["newsletter_drafted_on"] = today.isoformat()
    save_state(state)
    rc = 0
    if send and kit.configured():
        try:
            tags = kit.setup(scout.owner_emails(settings))
            kit.create_broadcast(subject, "Svar JA i arket for å publisere", preview_html,
                                 tag_id=tags["owner"], send_at=kit.soon(3), description=f"Preview {code}")
            report.append(f"\nPreview emailed to IK Start's approvers. Answer in the sheet with code **{code}**.")
        except kit.KitError as e:
            report.append(f"\n**The preview email could not be sent:** {e}")
            rc = 4
    elif send:
        report.append("\nKit is not connected yet, so no preview email was sent (add the KIT_API_KEY secret).")
    report.append(f"\nThe draft is saved in `pending/`. Approve it in the sheet's approvals tab with code **{code}**.")
    (PENDING / "report.md").write_text("\n".join(report), encoding="utf-8")
    (OUT / "report.md").write_text("\n".join(report), encoding="utf-8")
    log("\n".join(report))
    return rc


# ---------- publishing ----------

def _next_send_time(c: dict) -> datetime:
    tz = ZoneInfo(c["timezone"])
    hh, mm = map(int, c["newsletter"]["send_time_local"].split(":"))
    now = datetime.now(tz)
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return target if target > now + timedelta(minutes=5) else kit.soon(5)


def publish(send: bool = True, approved_by: str = "") -> list[str]:
    p = load_pending()
    if not p:
        return ["Nothing waiting for approval."]
    state, c, done = load_state(), club(), []
    if p["plan"].get("website") and (PENDING / "site.json").exists():
        SITE_FEED.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(PENDING / "site.json", SITE_FEED)
        state["website_fingerprint"] = p["fingerprint"]
        done.append("Website updated.")
    if p["plan"].get("newsletter") and (PENDING / "newsletter.html").exists():
        nl = json.loads((PENDING / "drafts.json").read_text(encoding="utf-8"))["newsletter"]
        issue = p.get("issue") or state["issue_number"] + 1
        if send and kit.configured():
            tags = kit.setup([])
            send_at = _next_send_time(c)
            kit.create_broadcast(nl["subject"], nl["preview_text"], (PENDING / "newsletter.html").read_text(encoding="utf-8"),
                                 tag_id=tags["fan"], send_at=send_at, description=f"Game Update #{issue}",
                                 public=c["newsletter"].get("public_web_archive", False))
            done.append(f"Game Update #{issue} scheduled for {send_at.astimezone(ZoneInfo(c['timezone'])):%A %d %b %H:%M}.")
        else:
            done.append(f"Game Update #{issue} approved (not sent: Kit is not connected).")
        state["issue_number"] = issue
        state["last_newsletter"] = p.get("date")
    state["history"].append({"code": p["code"], "approved_by": approved_by,
                             "at": datetime.now(timezone.utc).isoformat(timespec="minutes"), "done": done})
    save_state(state)
    clear_pending()
    return done


# ---------- the scheduled run ----------

def current_slot(c: dict, now: datetime) -> str | None:
    """'2026-10-27@07' for the latest draft time that has passed today, else None."""
    hours = [h for h in c.get("draft_hours_local", [7, 19]) if h <= now.hour]
    return f"{now.date().isoformat()}@{max(hours):02d}" if hours else None


def cmd_tick(args) -> int:
    c, state = club(), load_state()
    now = now_local()
    pending = load_pending()

    # 1. Has IK Start answered the draft that is waiting?
    if pending:
        decision = approvals.decision_for(scout.read_tab(args.source, "approvals"), pending["code"])
        if decision and decision["decision"] == "approve":
            done = publish(send=not args.no_send, approved_by=decision["by"])
            log(f"## {pending['code']} approved{(' by ' + decision['by']) if decision['by'] else ''}\n" +
                "\n".join(f"- {d}" for d in done))
            _gh_output(changed="yes", published="yes")
            return 0
        if decision and decision["decision"] == "stop":
            clear_pending()
            log(f"## {pending['code']} was rejected (NEI). The draft was thrown away.")
            _gh_output(changed="yes")
            return 0
        if decision and decision["decision"] == "changes":
            log(f"## {pending['code']}: IK Start asked for changes. Rewriting.")
            rc = draft(args.source, pending["plan"], decision["feedback"],
                       code=approvals.next_revision(pending["code"]), send=not args.no_send)
            _gh_output(changed="yes")
            return rc
        created = datetime.fromisoformat(pending["created"])
        if datetime.now(timezone.utc) - created > timedelta(days=PENDING_DAYS):
            clear_pending()
            log(f"## {pending['code']} expired after {PENDING_DAYS} days without an answer.")
            _gh_output(changed="yes")
            pending = None

    # 2. Is it time to look for news (07:00 / 19:00)?
    slot = current_slot(c, now)
    if not slot or slot == state.get("last_slot"):
        print("Nothing to do right now.")
        return 0
    state["last_slot"] = slot
    save_state(state)
    _gh_output(changed="yes")
    data = scout.collect(args.source, today_local())
    plan = make_plan("auto", data, state, today_local(), c)
    if pending:
        # A draft is still waiting. Redo it only if the sheet changed or the newsletter is due.
        if data["fingerprint"] == pending["fingerprint"] and not (plan["newsletter"] and not pending["plan"]["newsletter"]):
            print(f"{pending['code']} is still waiting for an answer.")
            return 0
        plan = {k: plan[k] or pending["plan"].get(k, False) for k in ("newsletter", "website")}
        plan["website"] = True
        return draft(args.source, plan, pending.get("feedback", ""), send=not args.no_send, data=data,
                     code=approvals.next_revision(pending["code"]) if plan["newsletter"] == pending["plan"]["newsletter"] else None)
    if not (plan["newsletter"] or plan["website"]):
        print("No news in the sheet since the last update.")
        return 0
    return draft(args.source, plan, send=not args.no_send, data=data)


def cmd_draft(args) -> int:
    """Manual draft (GitHub: Actions → Run workflow)."""
    c, state = club(), load_state()
    data = scout.collect(args.source, today_local())
    plan = make_plan(args.mode, data, state, today_local(), c)
    if not (plan["newsletter"] or plan["website"]):
        log("No news in the sheet since the last update, so there is nothing to draft. "
            "Choose mode 'newsletter' or 'website' to draft anyway.")
        return 0
    rc = draft(args.source, plan, args.feedback, send=not args.no_send, data=data)
    _gh_output(changed="yes")
    return rc


def cmd_publish(args) -> int:
    """Publish the waiting draft without the sheet (for emergencies)."""
    done = publish(send=not args.no_send, approved_by="manual")
    log("\n".join(done))
    _gh_output(changed="yes", published="yes")
    return 0


def cmd_demo(args) -> int:
    os.environ.setdefault("LLM_PROVIDER", "demo")
    os.environ.setdefault("AGENT_TODAY", "2026-10-05")  # the day after the sample results
    os.environ.setdefault("SITE_URL", (ROOT / "docs").as_uri())
    state_backup = STATE.read_text() if STATE.exists() else None
    pending_backup = PENDING.exists()
    try:
        data = scout.collect("sample", today_local())
        rc = draft("sample", {"newsletter": True, "website": True}, send=False, data=data)
    finally:  # the demo never changes the real state
        if state_backup is not None:
            STATE.write_text(state_backup)
        if not pending_backup:
            clear_pending()
    print(f"\nOpen {OUT / 'newsletter_preview.html'} to see the approvers' preview email.")
    return rc


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="agent.run")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tick")
    t.add_argument("--source", default="sheet", choices=["sheet", "sample"])
    t.add_argument("--no-send", action="store_true")
    d = sub.add_parser("draft")
    d.add_argument("--mode", default="auto", choices=["auto", "newsletter", "website"])
    d.add_argument("--source", default="sheet", choices=["sheet", "sample"])
    d.add_argument("--feedback", default=os.environ.get("FEEDBACK", ""))
    d.add_argument("--no-send", action="store_true")
    pub = sub.add_parser("publish")
    pub.add_argument("--no-send", action="store_true")
    sub.add_parser("demo")
    args = p.parse_args(argv)
    try:
        return {"tick": cmd_tick, "draft": cmd_draft, "publish": cmd_publish, "demo": cmd_demo}[args.cmd](args)
    except scout.DataError as e:
        log("## The club sheet needs a fix\nNothing was drafted or sent.\n\n" + str(e))
        print(str(e), file=sys.stderr)
        return 3
    except llm.LLMError as e:
        log("## The AI could not be reached\nNothing was sent. Check the GEMINI_API_KEY secret "
            "(GitHub → Settings → Secrets and variables → Actions).\n\n" + str(e))
        return 5


if __name__ == "__main__":
    sys.exit(main())
