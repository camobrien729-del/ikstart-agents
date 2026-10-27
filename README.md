# IK Start agents

A small team of AI agents that keeps the IK Start website (Kvinner and Herrer) up to date and writes the weekly **Game Update** newsletter. **Nothing is published until someone at IK Start types `JA` in the club sheet.**

**Cost: 0 kr.** Everything runs on free plans: GitHub (runs the agents, hosts the website), Google Sheets (the club's facts and approvals), Gemini (the AI) and Kit (sends the newsletter, free up to 10,000 subscribers).

| What | Where |
|---|---|
| Website | https://camobrien729-del.github.io/ikstart-agents/ |
| Club sheet (facts + approvals) | Google Sheet "IK Start club sheet (agents)" |
| Agents and settings | This GitHub repository |
| Newsletter sending, subscribers, stats | kit.com |

## How a week works

```
07:00 and 19:00 (Norway)   SCOUT reads the club sheet: matches, tables, notes.
                           If something changed, or it's Monday (newsletter day):
                           WEB WRITER + NEWSLETTER WRITER draft the update (AI),
                           FACT-CHECKER checks every number, score, quote and link against the sheet,
                           and the approvers get a PREVIEW EMAIL with a code, e.g. GU12.

Approver, any time         Opens the club sheet → tab "approvals" → adds a row:
                             GU12 | JA                              → publish
                             GU12 | ENDRE | "Lead with the result"  → new draft (GU12B) arrives
                             GU12 | NEI                             → throw it away

Every 30 minutes           The agents check the approvals tab. On JA: the website updates within
                           a few minutes and the newsletter is scheduled for Monday 12:00 in Kit.
```

**Why the facts are right:** the AI never types a score, date, kickoff, venue, table or ticket link. Code copies those straight from the sheet. The AI only writes the sentences around them, and the Fact-Checker blocks anything with a number, quote or link that isn't in the sheet. If information is missing, the draft is held back rather than guessed.

## The club's weekly job (about 5 minutes)

After each match, in the club sheet:
- **matches**: add `home_goals`, `away_goals`, `scorers` (separate with `;`), `attendance`, and set `status` to `played`. Add upcoming matches as new rows (date like `2026-10-24`, kickoff like `13:00`, `ticket_url` for home games).
- **table**: update the league table for each team.
- **notes**: optional extras (player spotlight, coach quote with the exact words, news, events, giveaways, partners, volunteers).

Then wait for the preview email and answer it in the **approvals** tab.

## Running it by hand

GitHub → **Actions** → *IK Start agents* → **Run workflow**:
- `check`: the normal run (look for answers, draft at 07:00/19:00)
- `newsletter`: write a Game Update right now
- `website`: write a website update right now
- `feedback` (optional): instructions for the writers, e.g. "Focus on the finale tickets"

Every run's result (what was drafted, what failed, what was published) is shown on its run page.

## Settings

| Setting | Where |
|---|---|
| Who approves (gets preview emails) | Sheet → settings → `owner_emails` |
| Newsletter sign-up link on the website | Sheet → settings → `newsletter_signup_link` |
| Newsletter day and time, draft hours, team names, links | `club.json` |
| Language (`nb` or `en`) | `club.json` → `language` |
| AI key | GitHub → Settings → Secrets → `GEMINI_API_KEY` |
| Kit key | GitHub → Settings → Secrets → `KIT_API_KEY` |
| Which sheet the agents read | `club.json` → `sheet_id` (the long code in the sheet's address) |
| Custom website address | GitHub → Settings → Variables → `SITE_URL` (only if you add your own domain) |

The sheet must be shared as **Anyone with the link → Viewer** so the agents can read it. Only people you add as **Editor** can change facts or approve.

Kit is set up automatically on the first run: the agents create the tags `ikstart-owners` (approvers) and `game-update-fans` (newsletter list) and add the approvers from the sheet.

## Moving it to IK Start

See **[HANDOFF.md](HANDOFF.md)**. It takes about 30 minutes and nothing has to be rebuilt.

## Files

| Path | What it is |
|---|---|
| `agent/scout.py` | Scout: reads and checks the club sheet |
| `agent/writers.py`, `agent/prompts.py` | Web Writer and Newsletter Writer, and their instructions |
| `agent/checker.py` | Fact-Checker |
| `agent/approvals.py` | Reads JA / ENDRE / NEI from the sheet |
| `agent/render.py`, `templates/` | Builds the email and the website feed from the facts |
| `agent/kit.py` | Sends through Kit |
| `agent/run.py` | Runs everything (`tick`, `draft`, `publish`, `demo`) |
| `docs/` | The website (GitHub Pages). `docs/data/site.json` is what the agents update |
| `pending/` | The draft waiting for approval (appears only while one is waiting) |
| `state/state.json` | Issue number and history |
| `.github/workflows/` | The schedule |
| `sheet_template/` | Blank copies of the sheet tabs |

Test locally: `pip install -r requirements.txt`, then `python -m agent.run demo` (no AI, nothing sent) and `python tests/test_checker.py && python tests/test_flow.py`.

## Limits to know
- **Facts come from the sheet.** Fixtures can be pulled automatically from fotball.no only through IK Start's data feed (FIKS). If IK Start gets access, a reader can replace the matches and table tabs.
- **GitHub's schedule can run a few minutes late** at busy times. Approvals are picked up within about 30–45 minutes.
- **A draft waits 7 days** for an answer, then is dropped.
- **The AI can still write a clumsy sentence.** That's why every update waits for a person.
