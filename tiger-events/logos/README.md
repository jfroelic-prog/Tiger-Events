# Logos

This folder fills itself. Each time `update_events.py` runs, it looks at
every upcoming opponent in the Bound feed and downloads any logo that's
missing (from that game's Bound page), resized to 96px. The header marks
`tech.png` and `crush.png` are fetched the same way on first run.

The first run pulls logos for the whole visible schedule (58 opponents
through May 2027); after that it only grabs new ones as winter and spring
schedules get posted.

## Filenames

Lowercase opponent name with spaces and punctuation removed:

- "Sauk Rapids-Rice" → `saukrapidsrice.png`
- "Zimmerman/Elk River/Rogers" → `zimmermanelkriverrogers.png`
- "St. Cloud Apollo" → `stcloudapollo.png`

## Fixing a wrong logo

Drop your own PNG in with the same filename and commit it — the updater
never overwrites a file that already exists.

To hide a team's logo (show a monogram square instead), add the team name
to `LOGO_SKIP` in `update_events.py`. "Elk River/Zimmerman" is already
there because Bound attaches a Centennial/Spring Lake Park image to it.
