# Handing the agents over to IK Start

After the class, IK Start takes ownership of everything. Nothing is rebuilt. About **30 minutes**, done together on a call.

Before you start, IK Start needs:
- one Google account (e.g. the club's shared Gmail or Google Workspace account)
- one GitHub account (free; create an *organization* such as `ikstart` if they want several people to have access)
- the email address of each person who should approve updates

## 1. The GitHub repository (runs the agents and the website)
1. Cam: repository → **Settings** → bottom of the page → **Transfer ownership** → type IK Start's GitHub account or organization → confirm.
2. IK Start: accept the transfer email.
3. IK Start: **Settings → Pages** → check that *Source* is **GitHub Actions**.
   The website moves to `https://<ikstart-account>.github.io/ikstart-agents/`. The agents pick up the new address automatically.
4. IK Start: **Settings → Secrets and variables → Actions**. Check that the secrets `GEMINI_API_KEY` and `KIT_API_KEY` are still there. In step 3 and 4 below you replace the keys with IK Start's own.
5. IK Start: **Actions** tab → if GitHub asks, click **Enable workflows**.
6. Cam: remove yourself under **Settings → Collaborators** if IK Start wants that.

## 2. The club sheet (facts and approvals)
1. Cam: open the sheet → **Share** → add IK Start's Google account as **Editor**.
2. Cam: next to their name, choose **Transfer ownership** (works between ordinary Gmail accounts).
   - If IK Start uses Google Workspace and the transfer isn't allowed: IK Start opens the sheet → **File → Make a copy**, sets the copy to **Share → Anyone with the link → Viewer**, and pastes the new sheet's ID (the long code in its address between `/d/` and `/edit`) into `club.json` → `sheet_id` (click the file in GitHub → pencil icon → Commit).
3. IK Start: in the sheet's **settings** tab, set `owner_emails` to the approvers' addresses.
4. Add the volunteers who update results as **Editors**. Anyone who is an Editor can also approve.

## 3. The AI key (Gemini)
1. IK Start: aistudio.google.com → sign in with the club's Google account → **Get API key** → create.
2. GitHub → Settings → Secrets and variables → Actions → `GEMINI_API_KEY` → **Update** → paste.

## 4. The newsletter (Kit)
Easiest: **IK Start gets their own free Kit account** and the subscriber list is moved over.
1. IK Start: create a free account at kit.com with the club's email.
2. Cam (old Kit account): **Subscribers** → select all → **Export** (CSV).
3. IK Start (new Kit account): **Subscribers → Import** → upload the CSV → add the tag `game-update-fans`.
4. IK Start: **Settings → Developer → API keys (v4)** → create → paste into the GitHub secret `KIT_API_KEY`.
5. IK Start: **Settings → Email** → set the sender to a club address (e.g. `nyhetsbrev@ikstart.no`) and add the DNS records Kit shows (the club's web provider can do this in 5 minutes). This keeps the Game Update out of spam folders.
6. IK Start: create a Kit **form** for the website sign-up (Grow → Landing pages & forms), make it add the tag `game-update-fans`, and paste its link into the sheet's settings tab → `newsletter_signup_link`.

The agents create the `ikstart-owners` tag and add the approvers automatically on the next run.

## 5. Test it
GitHub → **Actions** → *IK Start agents* → **Run workflow** → mode `newsletter`.
Within a few minutes the approvers get a preview email with a code. Add `code | NEI` in the approvals tab to throw the test away (or `JA` to send it).

## Optional: use the club's own web address
GitHub → Settings → Pages → **Custom domain** → e.g. `kamper.ikstart.no`, and add the DNS record GitHub shows. Then set the GitHub variable `SITE_URL` to `https://kamper.ikstart.no` so the newsletter images load from there.

## Who to contact
- The agents' code: this repository's README explains every file.
- Kit: help.kit.com
- GitHub Pages and Actions: docs.github.com
