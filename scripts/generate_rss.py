#!/usr/bin/env python3
"""
Generate a podcast RSS feed (iTunes / Spotify compatible) from the weekly
podcasts that have been uploaded to GitHub Releases.

Output: docs/feed.xml — committed to the repo and served via GitHub Pages
(branch=main, dir=/docs) at https://<user>.github.io/<repo>/feed.xml

(GitHub Pages only allows / or /docs as the source folder, so we use /docs.)

Required environment variables:
    GH_REPO     "owner/repo" — e.g. "tnvsh0/psychiatry-weekly-review"
                (also accepts GITHUB_REPOSITORY which Actions sets automatically)

Optional environment variables:
    GH_TOKEN    GitHub token for the releases API (higher rate limit).
                Optional for public repos but recommended.
    FEED_BASE_URL  Override the public URL of the feed (used in <atom:link>).
                   Defaults to GitHub Pages URL for the repo.
"""

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests


# Matches the "(N/M)" episode-number prefix that weekly_review.py embeds into
# the release title (e.g. "📚 (3/12) פסיכיאטריה ביולוגית — 2026-05-24").
EPISODE_NUM_RE = re.compile(r"\((\d+)\s*/\s*(\d+)\)")


# ── Playlists (Spotify / Apple "seasons") ─────────────────────────────────────
# The 10 weekly clusters generate too many episodes to scan visually, so we
# group them into 9 themed playlists. Each playlist is an iTunes "season"
# (numeric only — there's no <itunes:season-name> standard tag, so playlist
# IDENTITY lives in the episode title prefix `[ילד]`, `[נוירומדע]`, etc.).
PLAYLISTS: dict[int, dict] = {
    1: {"id": "child_psychiatry",      "he": "פסיכיאטריית הילד והמתבגר",
        "en": "Child & Adolescent Psychiatry",  "tag_he": "ילד"},
    2: {"id": "child_development",     "he": "התפתחות הילד",
        "en": "Child Development",              "tag_he": "התפתחות"},
    3: {"id": "general_psychiatry",    "he": "פסיכיאטריה כללית",
        "en": "General Psychiatry",             "tag_he": "כללית"},
    4: {"id": "biological_psychiatry", "he": "פסיכיאטריה ביולוגית",
        "en": "Biological Psychiatry",          "tag_he": "ביולוגית"},
    5: {"id": "neuroscience",          "he": "מדעי המוח",
        "en": "Neuroscience",                   "tag_he": "נוירומדע"},
    6: {"id": "cognition",             "he": "קוגניציה",
        "en": "Cognition",                      "tag_he": "קוגניציה"},
    7: {"id": "psychotherapy",         "he": "פסיכותרפיה",
        "en": "Psychotherapy",                  "tag_he": "פסיכותרפיה"},
    8: {"id": "behavioral_sciences",   "he": "מדעי ההתנהגות",
        "en": "Behavioral Sciences",            "tag_he": "התנהגות"},
    9: {"id": "spotlight_reviews",     "he": "מאמרי סקירה מובחנים",
        "en": "Spotlight Reviews",              "tag_he": "סקירה"},
}

# Routes a regular topic_id to its playlist number. Note that 3 child clusters
# all collapse into playlist 1 — that's the whole point of playlists.
TOPIC_TO_PLAYLIST: dict[str, int] = {
    "child_adolescent_core":           1,
    "child_adolescent_highimpact":     1,
    "child_adolescent_misc":           1,
    "child_development":               2,
    "general_psychiatry_clinical":     3,
    "general_psychiatry_bio":          4,
    "neuroscience":                    5,
    "cognition":                       6,
    "psychotherapy":                   7,
    "behavioral_sciences":             8,
    # spotlight_<pmid> handled separately by examining release title
}

# Keywords (Hebrew + English) that route a spotlight review into the child
# psychiatry playlist (1) instead of the generic spotlight playlist (9).
CHILD_PSYCH_KEYWORDS: list[str] = [
    "child", "adolescent", "pediatric", "paediatric", "youth", "infant",
    "school-age", "preschool", "perinatal",
    "ADHD", "attention-deficit", "attention deficit",
    "autism", "ASD", "autistic",
    "ילד", "ילדים", "מתבגר", "מתבגרים", "פדיאטר", "אוטיזם",
]


def _topic_id_base(topic_id: str) -> str:
    """Strip auto-split suffix so `child_adolescent_core_part2` maps to the
    same playlist as `child_adolescent_core`."""
    if "_part" in topic_id:
        return topic_id.rsplit("_part", 1)[0]
    return topic_id


def get_playlist_number(topic_id: str, release_name: str = "") -> int:
    """Return the playlist (=iTunes season) number for an episode.

    Regular topics use TOPIC_TO_PLAYLIST. Spotlight reviews are routed by
    title content — child-related ones join the child playlist; otherwise
    they go to the spotlight playlist."""
    base = _topic_id_base(topic_id)
    if base in TOPIC_TO_PLAYLIST:
        return TOPIC_TO_PLAYLIST[base]
    if base.startswith("spotlight_"):
        name_lower = release_name.lower()
        if any(kw.lower() in name_lower for kw in CHILD_PSYCH_KEYWORDS):
            return 1
        return 9
    return 9  # safe default — anything unknown lands in the catch-all playlist


# Topic labels — id -> (Hebrew title, English title, episode description).
# Kept in sync with the TOPICS list in weekly_review.py.
TOPIC_LABELS: dict[str, tuple[str, str, str]] = {
    "child_adolescent_core": (
        "ליבה — פסיכיאטריית ילד ומתבגר",
        "Child & Adolescent Psychiatry — Core",
        "סקירה שבועית של כתבי העת המרכזיים בפסיכיאטריית הילד והמתבגר.",
    ),
    "child_adolescent_highimpact": (
        "השפעה גבוהה — ילד ומתבגר",
        "Child & Adolescent — High Impact",
        "מאמרים בעלי השפעה גבוהה בנושאי ילד/מתבגר מכתבי עת רפואיים מובילים.",
    ),
    "general_psychiatry_clinical": (
        "פסיכיאטריה כללית — קלינית",
        "General Psychiatry — Clinical",
        "סקירה קלינית של פסיכיאטריה כללית — שיזופרניה, דיכאון, חרדה, התאבדות.",
    ),
    "general_psychiatry_bio": (
        "פסיכיאטריה ביולוגית",
        "Biological Psychiatry",
        "מחקר ביולוגי ופסיכופרמקולוגי — מנגנונים, גנטיקה, וטיפולים תרופתיים.",
    ),
    "child_development": (
        "התפתחות הילד",
        "Child Development",
        "מחקרי התפתחות, התקשרות, הורות, התערבות מוקדמת, וטראומה.",
    ),
    "neuroscience": (
        "מדעי המוח",
        "Neuroscience",
        "ממצאי מדעי המוח הרלוונטיים לפסיכיאטריה ולהתפתחות מוחית.",
    ),
    "psychotherapy": (
        "פסיכותרפיה והתערבויות",
        "Psychotherapy & Interventions",
        "מחקר עדכני בפסיכותרפיה — CBT, DBT, התערבויות לילדים ומבוגרים.",
    ),
    "behavioral_sciences": (
        "מדעי ההתנהגות",
        "Behavioral Sciences",
        "למידה, חיזוק וקוגניציה חברתית.",
    ),
    "cognition": (
        "קוגניציה ומדעי הקוגניציה",
        "Cognition & Cognitive Science",
        "התפתחות קוגניטיבית, תפקודים ניהוליים, וזיכרון עבודה.",
    ),
    "child_adolescent_misc": (
        "ילדים ומתבגרים — מגוון",
        "Child & Adolescent — Miscellaneous",
        "מאמרים מגוונים בנושאי ילד/מתבגר מכתבי עת שאינם בליבה.",
    ),
}


PODCAST_TITLE = "סקירה שבועית בפסיכיאטריה"
PODCAST_DESCRIPTION = (
    "סקירה שבועית בעברית של המאמרים המרכזיים בפסיכיאטריה, "
    "פסיכיאטריית הילד והמתבגר, התפתחות, נוירולוגיה, פסיכותרפיה וקוגניציה. "
    "מבוסס על PubMed ומופק אוטומטית מדי שבוע. "
    "אינו מהווה ייעוץ רפואי."
)
PODCAST_AUTHOR = "Tovia Wen"
PODCAST_EMAIL = "toviagpt@gmail.com"
PODCAST_LANGUAGE = "he"
PODCAST_CATEGORY = "Health & Fitness"
PODCAST_SUBCATEGORY = "Medicine"

# Cover image — required by Apple Podcasts, recommended by Spotify.
# Hosted on GitHub Pages alongside the feed itself. The default URL works
# for the production deployment; override via PODCAST_IMAGE_URL env var if
# you're testing locally or hosting elsewhere.
PODCAST_IMAGE_URL_DEFAULT = "https://tnvsh0.github.io/psychiatry-weekly-review/cover.png"


def _resolve_repo() -> str:
    repo = os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY", "")
    if not repo or "/" not in repo:
        print("ERROR: GH_REPO (or GITHUB_REPOSITORY) must be set, e.g. 'owner/repo'")
        sys.exit(1)
    return repo


def _gh_headers() -> dict:
    h = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _fetch_releases(repo: str) -> list[dict]:
    """List all releases (paginated). Returns the raw release dicts."""
    out: list[dict] = []
    page = 1
    while True:
        r = requests.get(
            f"https://api.github.com/repos/{repo}/releases",
            headers=_gh_headers(),
            params={"per_page": 100, "page": page},
            timeout=30,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return out


def _parse_tag(tag: str) -> tuple[str, str] | None:
    """Parse 'weekly-YYYY-MM-DD-{topic_id}' → (date, topic_id)."""
    if not tag.startswith("weekly-"):
        return None
    rest = tag[len("weekly-"):]
    parts = rest.split("-", 3)
    if len(parts) < 4:
        return None
    date_str = "-".join(parts[:3])
    topic_id = parts[3]
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None
    return date_str, topic_id


def _audio_duration_seconds(local_mp3: Path) -> int | None:
    """Return duration in seconds, or None if mutagen is not available."""
    if not local_mp3.exists():
        return None
    try:
        from mutagen.mp3 import MP3
    except ImportError:
        return None
    try:
        return int(MP3(str(local_mp3)).info.length)
    except Exception:
        return None


def build_feed(repo: str, out_path: Path) -> None:
    try:
        from feedgen.feed import FeedGenerator
    except ImportError:
        print("ERROR: feedgen not installed. pip install feedgen")
        sys.exit(2)

    owner = repo.split("/", 1)[0]
    repo_name = repo.split("/", 1)[1]
    default_feed_url = f"https://{owner}.github.io/{repo_name}/feed.xml"
    feed_url = os.environ.get("FEED_BASE_URL", default_feed_url)
    site_url = f"https://github.com/{repo}"

    fg = FeedGenerator()
    fg.load_extension("podcast")
    fg.title(PODCAST_TITLE)
    fg.link(href=site_url, rel="alternate")
    fg.link(href=feed_url, rel="self")
    fg.description(PODCAST_DESCRIPTION)
    fg.language(PODCAST_LANGUAGE)
    fg.author({"name": PODCAST_AUTHOR, "email": PODCAST_EMAIL})
    fg.podcast.itunes_author(PODCAST_AUTHOR)
    fg.podcast.itunes_summary(PODCAST_DESCRIPTION)
    fg.podcast.itunes_owner(name=PODCAST_AUTHOR, email=PODCAST_EMAIL)
    fg.podcast.itunes_explicit("no")
    fg.podcast.itunes_category(PODCAST_CATEGORY, PODCAST_SUBCATEGORY)
    fg.podcast.itunes_type("episodic")
    # Cover image — Apple Podcasts will reject the feed without this.
    image_url = os.environ.get("PODCAST_IMAGE_URL", PODCAST_IMAGE_URL_DEFAULT)
    fg.podcast.itunes_image(image_url)
    fg.image(image_url, PODCAST_TITLE, site_url)

    print(f"Fetching releases from {repo}...")
    releases = _fetch_releases(repo)
    print(f"  Found {len(releases)} release(s).")

    repo_root = Path(__file__).resolve().parent.parent

    episodes = 0
    for rel in releases:
        tag = rel.get("tag_name", "")
        parsed = _parse_tag(tag)
        if not parsed:
            continue
        date_str, topic_id = parsed
        # Extract episode number (e.g. "(3/12)") from the release title if
        # present. Older releases (pre-numbering) simply have no match here.
        rel_name_raw = rel.get("name", "")
        ep_match = EPISODE_NUM_RE.search(rel_name_raw)
        ep_prefix = f"({ep_match.group(1)}/{ep_match.group(2)}) " if ep_match else ""

        labels = TOPIC_LABELS.get(topic_id)
        if not labels:
            # Spotlight reviews use dynamic topic_ids of the form
            # `spotlight_{pmid}`. Pull the actual article title from the
            # release's own name (which carries it verbatim from the
            # weekly_review.py side).
            if topic_id.startswith("spotlight_"):
                rel_name = rel_name_raw.replace("📚 ", "").strip()
                # Drop the episode-number prefix from the embedded title — we
                # re-attach a clean prefix below.
                rel_name = EPISODE_NUM_RE.sub("", rel_name, count=1).strip()
                parts = rel_name.split(" — ")
                # Trailing segment is the YYYY-MM-DD; everything before is title.
                if len(parts) > 1:
                    episode_title_he = " — ".join(parts[:-1]).strip()
                else:
                    episode_title_he = rel_name or "מאמר סקירה מרכזי"
                labels = (
                    episode_title_he,
                    "Spotlight Review",
                    "פודקאסט ייעודי על מאמר סקירה מרכזי מהשבוע — "
                    "סקירה ארוכה ומעמיקה של מאמר בודד.",
                )
            else:
                continue
        label_he, label_en, topic_desc = labels

        assets = rel.get("assets", [])
        if not assets:
            continue
        asset = assets[0]
        audio_url = asset.get("browser_download_url")
        audio_size = int(asset.get("size", 0))
        if not audio_url:
            continue

        try:
            pub_date = datetime.strptime(date_str, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue

        local_mp3 = repo_root / "podcasts" / date_str / f"{topic_id}.mp3"
        duration = _audio_duration_seconds(local_mp3)

        # Playlist routing — every episode belongs to exactly one of the 9
        # themed playlists. We emit <itunes:season>N</itunes:season> so podcast
        # apps that respect seasons display them as separate tabs, and we
        # prefix the title with the playlist tag (`[ילד]`, `[נוירומדע]`, …)
        # so listeners can identify the playlist even in apps that don't
        # render seasons.
        playlist_num = get_playlist_number(topic_id, rel_name_raw)
        playlist = PLAYLISTS[playlist_num]
        playlist_tag = f"[{playlist['tag_he']}] "

        # Episode number prefix (e.g. "(3/12) ") tracks within-week progress.
        title = f"{playlist_tag}{ep_prefix}{label_he} — {date_str}"
        description = (
            f"{topic_desc}\n\n"
            f"פלייליסט: {playlist['he']} ({playlist['en']}).\n\n"
            f"סקירה אוטומטית מ-{date_str}.\n\n"
            f"{label_en}"
        )

        fe = fg.add_entry()
        fe.id(audio_url)
        fe.title(title)
        fe.description(description)
        fe.enclosure(audio_url, str(audio_size), "audio/mpeg")
        fe.pubDate(pub_date)
        fe.podcast.itunes_summary(description)
        fe.podcast.itunes_author(PODCAST_AUTHOR)
        fe.podcast.itunes_season(playlist_num)
        if duration is not None:
            fe.podcast.itunes_duration(duration)
        episodes += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fg.rss_file(str(out_path), pretty=True)
    print(f"  Wrote {episodes} episode(s) to {out_path}")


def main() -> int:
    repo = _resolve_repo()
    out_path = Path(__file__).resolve().parent.parent / "docs" / "feed.xml"
    build_feed(repo, out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
