#!/usr/bin/env python3
"""
Generate a podcast RSS feed (iTunes / Spotify compatible) from the weekly
podcasts that have been uploaded to GitHub Releases.

Output: podcast/feed.xml — committed to the repo and served via GitHub Pages
(branch=main, dir=/podcast) at https://<user>.github.io/<repo>/feed.xml

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
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests


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
PODCAST_EMAIL = "tovia.wen@gmail.com"
PODCAST_LANGUAGE = "he"
PODCAST_CATEGORY = "Health & Fitness"
PODCAST_SUBCATEGORY = "Medicine"


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
        labels = TOPIC_LABELS.get(topic_id)
        if not labels:
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

        title = f"{label_he} — {date_str}"
        description = f"{topic_desc}\n\nסקירה אוטומטית מ-{date_str}.\n\n{label_en}"

        fe = fg.add_entry()
        fe.id(audio_url)
        fe.title(title)
        fe.description(description)
        fe.enclosure(audio_url, str(audio_size), "audio/mpeg")
        fe.pubDate(pub_date)
        fe.podcast.itunes_summary(description)
        fe.podcast.itunes_author(PODCAST_AUTHOR)
        if duration is not None:
            fe.podcast.itunes_duration(duration)
        episodes += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fg.rss_file(str(out_path), pretty=True)
    print(f"  Wrote {episodes} episode(s) to {out_path}")


def main() -> int:
    repo = _resolve_repo()
    out_path = Path(__file__).resolve().parent.parent / "podcast" / "feed.xml"
    build_feed(repo, out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
