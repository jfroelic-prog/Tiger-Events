#!/usr/bin/env python3
"""
Tiger Events updater — runs on your Mac via launchd.

Fetches the Bound (gobound.com) iCal feed for St. Cloud Tech, keeps
HOME events for the next two weeks, cleans up the titles, writes
events.json, and pushes it to GitHub so the Carousel bulletin
updates itself. Also downloads a logo for any opponent that doesn't
have one yet (from Bound's game pages), so new seasons fill in on their own.

Test by hand any time:  python3 update_events.py
"""

import html, json, os, re, subprocess, sys, urllib.request
from datetime import datetime, timedelta, date, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# ======================= CONFIG =======================
# Runs on GitHub's servers by default. The feed URL comes from the repo secret
# ICS_URL when one is set, so it stays out of the public repository.
ICS_URL = os.environ.get(
    "ICS_URL",
    "https://gobound.com/mn/schools/stcloudtech/calendar/ical/425f0eec539b4bc",
)
DAYS_AHEAD = 14        # keep two weeks; the page shows 5 days
HOME_ONLY = True
# An event is HOME when its location contains any of these.
# "st. cloud apollo" is included so co-op home games hosted at Apollo
# (e.g. Adapted Soccer) count as home; remove it to show only Tech-building events.
HOME_LOCATIONS = ["st. cloud tech", "st. cloud apollo"]
# How our own teams appear in Bound titles ("Visitor vs Home"),
# including co-ops (Crush hockey, St. Cloud/ROCORI, St. Cloud/SRR):
US_NAMES = {"st. cloud tech", "st cloud tech", "st. cloud", "st cloud",
            "st. cloud crush", "st. cloud/rocori", "st. cloud/srr"}
# Opponents whose Bound logo is wrong — they get a monogram instead.
LOGO_SKIP = {"Elk River/Zimmerman"}
LOGO_PX = 96           # opponent logo size (the sign shows them ~60px)
LOCAL_TZ = ZoneInfo("America/Chicago")
REPO_DIR = Path(__file__).resolve().parent
# ======================================================


def fetch_ics(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "TigerEvents/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


def unfold(text: str) -> list[str]:
    return re.sub(r"\n[ \t]", "", text.replace("\r\n", "\n")).split("\n")


def unescape(s: str) -> str:
    return (s.replace("\\n", ", ").replace("\\N", ", ")
             .replace("\\,", ",").replace("\\;", ";")
             .replace("\\\\", "\\").strip())


def parse_dtstart(key: str, val: str):
    """Return (iso_date, 'HH:MM' or '') in local wall time."""
    if re.fullmatch(r"\d{8}", val):
        return f"{val[0:4]}-{val[4:6]}-{val[6:8]}", ""
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})?(Z?)", val)
    if not m:
        return None, None
    y, mo, d, h, mi = (int(m.group(i)) for i in range(1, 6))
    if m.group(7) == "Z":
        dt = datetime(y, mo, d, h, mi, tzinfo=timezone.utc).astimezone(LOCAL_TZ)
    else:  # TZID=America/Chicago or floating — already local wall time
        dt = datetime(y, mo, d, h, mi)
    return dt.strftime("%Y-%m-%d"), f"{dt.hour:02d}:{dt.minute:02d}"


def parse_ics(text: str) -> list[dict]:
    events, cur = [], None
    for line in unfold(text):
        if line.startswith("BEGIN:VEVENT"):
            cur = {}
        elif line.startswith("END:VEVENT"):
            if cur and cur.get("date"):
                events.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            key, val = line.split(":", 1)
            name = key.split(";")[0].upper()
            if name == "SUMMARY":
                cur["summary"] = unescape(val)
            elif name == "LOCATION":
                cur["location"] = unescape(val)
            elif name == "URL":
                cur["url"] = val.strip()
            elif name == "DTSTART":
                d, t = parse_dtstart(key, val)
                if d:
                    cur["date"], cur["time"] = d, t
    return events


# ---------- Bound-specific cleanup ----------
# SUMMARY looks like:  "Soccer, Boys: Alexandria Area vs St. Cloud Tech (Varsity)"
# or an invite:        "Cross Country Running, Girls: ROCORI Invitational (Varsity)"

def is_us(name: str) -> bool:
    return name.lower().strip(" .") in {n.strip(" .") for n in US_NAMES}


def norm_activity(a: str) -> str:
    a = a.replace("Cross Country Running", "Cross Country")
    m = re.match(r"^(.*),\s*(Boys|Girls)$", a)
    if m:
        a = f"{m.group(2)} {m.group(1)}"
    return re.sub(r"\s+", " ", a).strip()


def split_summary(s: str):
    level = ""
    m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", s)
    if m:
        s, level = m.group(1), m.group(2).strip()
    if ":" in s:
        activity, rest = s.split(":", 1)
    else:
        activity, rest = s, ""
    return activity.strip(), rest.strip(), level


def build_event(ev: dict):
    summary = ev.get("summary", "")
    location = ev.get("location", "")
    activity, rest, level = split_summary(summary)
    activity = norm_activity(activity)

    opponent = ""
    us = "tech"    # which of our logos to show: Tech T, or Crush for co-op teams
    sides = re.split(r"\s+vs\.?\s+", rest, flags=re.I)
    if len(sides) == 2:
        a, b = sides[0].strip(), sides[1].strip()
        opponent = a if is_us(b) else b
        ours = b if is_us(b) else a
        if ours.lower().replace("st ", "st. ") != "st. cloud tech":
            us = "crush"
        title = f"{activity} vs. {opponent}" if activity else f"{a} vs. {b}"
    else:  # invitational / meet / section — no "vs"
        title = f"{activity} — {rest}" if (activity and rest) else (activity or rest or "Event")

    # "JV Football vs. ..." style prefix for sub-varsity levels
    if level and level.lower() != "varsity" and len(level) > 2 \
       and level.lower() not in title.lower():
        title = f"{level} {title}"

    # Bound lists "Visitor vs Home". Our building always counts as home;
    # a shared venue (Apollo) counts only when St. Cloud is the home side,
    # so Tech's away games AT Apollo stay off the sign.
    loc = location.lower()
    we_host = len(sides) == 2 and is_us(sides[1])
    if HOME_LOCATIONS[0] in loc:
        home = True
    elif any(k in loc for k in HOME_LOCATIONS[1:]):
        home = we_host
    else:
        home = we_host and not location

    venue = re.sub(r"^st\.?\s*cloud\s+tech\s+high\s+school\s*", "",
                   location, flags=re.I).strip(" -,") or "Tech High School"

    return {"title": title, "opponent": opponent, "us": us, "location": venue,
            "date": ev["date"], "time": ev.get("time", ""),
            "_home": home, "_activity": activity}


def merge_boys_girls(events: list[dict]) -> list[dict]:
    """'Boys Cross Country — X Invite' + 'Girls ...' same time/place -> one row."""
    out, seen = [], {}
    for e in events:
        base = re.sub(r"^(Boys|Girls)\s+", "", e["title"])
        key = (e["date"], e["time"], e["location"], base)
        if key in seen and e["title"] != seen[key]["title"]:
            seen[key]["title"] = f"Boys & Girls {base}"
        elif key not in seen:
            seen[key] = e
            out.append(e)
    return out


# ---------- logos ----------
def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def opponent_of(summary: str) -> str:
    _, rest, _ = split_summary(summary)
    sides = [x.strip() for x in re.split(r"\s+vs\.?\s+", rest, flags=re.I)]
    if len(sides) != 2:
        return ""
    if is_us(sides[1]):
        return sides[0]
    if is_us(sides[0]):
        return sides[1]
    return ""


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 TigerEvents/1.0"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read()


def find_logo_url(page: str, team: str, fallback_ok=True):
    norm = lambda x: re.sub(r"[^a-z]", "", x.lower())
    imgs = [(html.unescape(src), html.unescape(alt).strip()) for src, alt in
            re.findall(r'<img src="([^"]+-Large[^"]*\.(?:png|jpg))" alt="([^"]*) Logo"', page, re.I)]
    for src, alt in imgs:
        if norm(alt) == norm(team):
            return src
    first = norm(re.split(r"[/ ]", team)[0])
    for src, alt in imgs:
        if not is_us(alt) and norm(alt).startswith(first):
            return src
    return None


def save_logo(img_url: str, dest: Path, px: int):
    dest.parent.mkdir(exist_ok=True)
    tmp = dest.with_suffix(".download")
    tmp.write_bytes(http_get(img_url))
    # Pillow where it's installed (GitHub Actions), macOS sips otherwise,
    # and failing both, keep the image at its original size.
    try:
        from PIL import Image
        im = Image.open(tmp).convert("RGBA")
        im.thumbnail((px, px), Image.LANCZOS)
        im.save(dest, "PNG")
        tmp.unlink(missing_ok=True)
        return
    except Exception:
        pass
    r = subprocess.run(["sips", "-s", "format", "png", "-Z", str(px), str(tmp), "--out", str(dest)],
                       capture_output=True)
    if r.returncode != 0 or not dest.exists():
        tmp.replace(dest)
    else:
        tmp.unlink(missing_ok=True)


def sync_logos(raw: list[dict]) -> list[str]:
    """Download logos for upcoming opponents that don't have one yet."""
    logos = REPO_DIR / "logos"
    today = date.today().isoformat()
    pages = {}   # opponent -> [game page urls]
    for ev in raw:
        if ev["date"] < today or not ev.get("url"):
            continue
        opp = opponent_of(ev.get("summary", ""))
        if opp and opp not in LOGO_SKIP:
            pages.setdefault(opp, []).append(ev["url"])

    added = []
    for opp, urls in sorted(pages.items()):
        dest = logos / f"{slug(opp)}.png"
        if dest.exists():
            continue
        for u in urls[:5]:
            try:
                src = find_logo_url(http_get(u).decode("utf-8", "replace"), opp)
                if src:
                    save_logo(src, dest, LOGO_PX)
                    added.append(dest.name)
                    break
            except Exception as e:
                print(f"  logo {opp}: {e}")
    # Our own marks for the header, grabbed from any game page
    for team, name in (("St. Cloud Tech", "tech.png"), ("St. Cloud", "crush.png")):
        dest = logos / name
        if dest.exists():
            continue
        for ev in raw:
            if not ev.get("url"):
                continue
            try:
                page = http_get(ev["url"]).decode("utf-8", "replace")
                pat = r'<img src="([^"]+-Large[^"]*\.png)" alt="%s Logo"' % re.escape(team)
                m = re.search(pat, page)
                if m and (name != "crush.png" or "crush" in m.group(1).lower()):
                    save_logo(html.unescape(m.group(1)), dest, 200)
                    added.append(name)
                    break
            except Exception:
                continue
    return added


def git(*args):
    return subprocess.run(["git", "-C", str(REPO_DIR), *args],
                          capture_output=True, text=True)


def main():
    raw = parse_ics(fetch_ics(ICS_URL))

    new_logos = sync_logos(raw)
    if new_logos:
        print(f"Added {len(new_logos)} logos: {', '.join(new_logos)}")

    today = date.today()
    horizon = today + timedelta(days=DAYS_AHEAD)
    keep = []
    for ev in raw:
        d = date.fromisoformat(ev["date"])
        if not (today <= d <= horizon):
            continue
        e = build_event(ev)
        if HOME_ONLY and not e["_home"]:
            continue
        keep.append(e)
    keep.sort(key=lambda e: (e["date"], e["time"] or "00:00"))
    keep = merge_boys_girls(keep)
    for e in keep:
        e.pop("_home", None); e.pop("_activity", None)

    now = datetime.now(LOCAL_TZ)
    stamp = f"{now:%a} {now.strftime('%I').lstrip('0')}:{now:%M} {now:%p}"
    out = REPO_DIR / "events.json"

    # Skip the commit entirely if only the timestamp would change.
    try:
        same = json.loads(out.read_text()).get("events") == keep
    except Exception:
        same = False
    if same and not new_logos:
        print(f"No changes ({len(keep)} home events). Nothing pushed.")
        return
    if not same:
        out.write_text(json.dumps({"updated": stamp, "events": keep}, indent=2))
        print(f"Wrote {len(keep)} home events through {horizon}.")

    git("add", "events.json", "logos")
    c = git("commit", "-m", f"Update events {now:%Y-%m-%d %H:%M}")
    if c.returncode != 0:
        print("Nothing to commit."); return
    p = git("push")
    if p.returncode != 0:
        sys.exit("git push failed:\n" + p.stderr)
    print("Pushed. Signs update within ~10 minutes.")


if __name__ == "__main__":
    main()
