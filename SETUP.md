# Tiger Events — Setup

A self-updating home-events bulletin for Carousel. The page lives on GitHub
Pages and refreshes itself on GitHub's servers. **Nothing runs on a school
computer** — no Python process, no background job, nothing for endpoint
security to flag. Your Mac is only used to set this up once.

---

## 1. Create the GitHub repo

1. On github.com: **New repository** → name it `tiger-events` → **Public** →
   Create. (Public is required for free GitHub Pages.)
2. On the repo page, click **Add file → Upload files**, drag in everything
   from this folder — `index.html`, `events.json`, `update_events.py`,
   `logos/`, `.github/` — and click **Commit changes**.

   If Finder hides the `.github` folder, press **Cmd+Shift+.** to show
   hidden files. That folder is what makes the automatic updates work.

## 2. Turn on the web page

In the repo: **Settings → Pages → Branch: `main` / `(root)` → Save.**

After a minute or two your page is live at:
`https://YOUR-GITHUB-NAME.github.io/tiger-events/`

It already shows real home games, so you can point Carousel at it right away.

## 3. Point Carousel at it

In the Carousel editor, create a **Webpage bulletin** and paste that URL.
It's built for an 8.5x11 portrait zone. It shows **today's** home events on
one page — shrinking the rows if the day is packed — and fills any leftover
space with the next days' games under a "Coming up" heading.

## 4. Store the calendar feed

The feed URL lives in a repo secret rather than in the public code.

**Settings → Secrets and variables → Actions → New repository secret**

- Name: `ICS_URL`
- Secret: `https://gobound.com/mn/schools/stcloudtech/calendar/ical/425f0eec539b4bc`

## 5. Run it once

Open the **Actions** tab → **Update events** → **Run workflow**.

The first run takes a couple of minutes: it downloads a logo for every
opponent on the schedule (~58 teams), writes the events, and commits them.
When it finishes with a green check, reload your Pages URL — logos and the
current schedule should be there.

From then on it runs by itself at **6am, 10am, 2pm and 6pm Central**. To
change that, edit the `cron` line in `.github/workflows/update-events.yml`
(those times are written in UTC, which is Central + 5 hours).

---

## Day to day

Nothing. The sign follows the Bound feed on its own, including new opponents
and their logos as winter and spring schedules get posted.

To force an update right now (say a game time changed an hour before
tip-off), open **Actions → Update events → Run workflow**. Carousel picks up
the change within 10 minutes; the page re-checks that often.

### What the page shows

Today's home events, always on a single page. A busy day scales down to fit;
a quiet day fills the rest of the page with upcoming days, one whole day at a
time, only while they fit. Set `FILL_AHEAD: false` at the top of `index.html`
to show today only.

### What counts as a home event

Anything at St. Cloud Tech, plus co-op home games hosted at Apollo (Adapted
Soccer, etc.) — but not Tech's away games at Apollo. To change that, edit
`HOME_LOCATIONS` in `update_events.py`.

### Logos

Automatic — see `logos/README.md`. To replace one, upload your own PNG with
the same filename; the script never overwrites a file that already exists.

### If the schedule stops updating

GitHub pauses scheduled jobs on repos that sit untouched for 60 days, and
emails the repo owner when it does. The sign keeps showing the last good
schedule the whole time. To restart it: **Actions** tab → the banner's
**Enable workflow** button.

Otherwise, check **Actions** for a failed (red) run and open it to see why.
The most likely cause is the Bound feed URL changing — if so, update the
`ICS_URL` secret.

---

## Optional: running it from a Mac instead

Only do this if you'd rather not use GitHub Actions. It needs Python and a
scheduled job on the machine, which is what district endpoint protection
tends to flag — and it only updates while that Mac is awake.

```bash
git clone https://github.com/YOUR_USERNAME/tiger-events.git ~/tiger-events
cd ~/tiger-events
python3 update_events.py          # test it once by hand

sed -i '' "s|YOUR_USERNAME|$USER|" com.tigerevents.update.plist
cp com.tigerevents.update.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.tigerevents.update.plist
cat /tmp/tigerevents.log          # should show the same output as the manual run
```

Pushing from the Mac needs git to be signed in: `brew install gh && gh auth
login`, answering **Yes** to "Authenticate Git with your GitHub credentials?"

To remove it later:

```bash
launchctl bootout gui/$(id -u)/com.tigerevents.update
```

To find every launchd job you've set up on a Mac (useful before replacing
one): `ls ~/Library/LaunchAgents/` and `crontab -l`.
