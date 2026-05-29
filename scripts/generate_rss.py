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


PODCAST_AUTHOR = "Tovia Wen"
PODCAST_EMAIL = "toviagpt@gmail.com"
PODCAST_LANGUAGE = "he"
PODCAST_CATEGORY = "Health & Fitness"
PODCAST_SUBCATEGORY = "Medicine"

# Base URL where covers and feeds are served — GitHub Pages by default.
DEFAULT_PAGES_BASE = "https://tnvsh0.github.io/psychiatry-weekly-review"


# ── Channels — one Spotify show per channel ───────────────────────────────────
# Three themed shows that each get their own RSS feed, cover image, and title.
# A 4th "combined" entry preserves the original feed.xml for the existing
# Spotify subscription (so anyone already following the old URL doesn't break).
#
# Spotlight reviews are routed by keyword in the article title:
#   * Child / adolescent / ADHD / autism / pediatric → channel "child"
#   * Psychotherapy / CBT / DBT / therapy           → channel "therapy"
#   * Everything else (pharmacology, genetics,
#     methodology, neuroscience, ...)               → channel "psychiatry"
THERAPY_KEYWORDS: list[str] = [
    "psychotherapy", "psycho-therapy",
    "CBT", "cognitive behavioral", "cognitive-behavioral", "cognitive behaviour",
    "DBT", "dialectical behavior", "dialectical behaviour",
    "MBT", "mentalization",
    "psychodynamic", "interpersonal therapy", "IPT",
    "intervention", "psychological treatment",
    "פסיכותרפיה", "טיפול פסיכולוגי", "טיפול קוגניטיבי",
]

# Standalone AI-disclosure line — appended to every channel description and
# every episode description so listeners encountering the show anywhere
# (Apple's directory, Spotify show page, a podcast app's notes pane)
# immediately see the disclaimer.
AI_DISCLOSURE = (
    "⚠️ התוכן נוצר באופן אוטומטי באמצעות בינה מלאכותית — אינו מהווה ייעוץ "
    "רפואי, חובה לבדוק כל פרט מול המקור המקורי."
)

CHANNELS: list[dict] = [
    {
        "id":          "child",
        "feed_file":   "feed-child.xml",
        "cover_file":  "cover-child.png",
        "title":       "סקירה שבועית — פסיכיאטריית הילד והמתבגר",
        "description": (
            "סקירה שבועית בעברית של המאמרים המרכזיים בפסיכיאטריית הילד "
            "והמתבגר ובהתפתחות הילד — מבוסס על PubMed ומופק אוטומטית מדי "
            "שבוע. כולל את ליבת הפסיכיאטריה של הילד, מאמרים רלוונטיים "
            "מכתבי עת רפואיים מובילים, ומאמרי סקירה משמעותיים.\n\n"
            f"{AI_DISCLOSURE}"
        ),
        "topic_ids":   [
            "child_adolescent_core",
            "child_adolescent_highimpact",
            "child_adolescent_misc",
            "child_development",
        ],
        "spotlight_routing": "child",
    },
    {
        "id":          "psychiatry",
        "feed_file":   "feed-psychiatry.xml",
        "cover_file":  "cover-psychiatry.png",
        "title":       "סקירה שבועית — פסיכיאטריה ומדעי המוח",
        "description": (
            "סקירה שבועית בעברית של המאמרים המרכזיים בפסיכיאטריה כללית "
            "(קלינית וביולוגית) ובמדעי המוח — מבוסס על PubMed ומופק "
            "אוטומטית מדי שבוע. כולל מאמרי סקירה משמעותיים בפסיכופרמקולוגיה "
            "ובמחקר ביולוגי.\n\n"
            f"{AI_DISCLOSURE}"
        ),
        "topic_ids":   [
            "general_psychiatry_clinical",
            "general_psychiatry_bio",
            "neuroscience",
        ],
        "spotlight_routing": "default",
    },
    {
        "id":          "therapy",
        "feed_file":   "feed-therapy.xml",
        "cover_file":  "cover-therapy.png",
        "title":       "סקירה שבועית — פסיכותרפיה וקוגניציה",
        "description": (
            "סקירה שבועית בעברית של המאמרים המרכזיים בפסיכותרפיה, "
            "במדעי ההתנהגות ובקוגניציה — מבוסס על PubMed ומופק אוטומטית "
            "מדי שבוע. כולל ראיות עדכניות על CBT, DBT, התערבויות "
            "פסיכולוגיות, מנגנונים קוגניטיביים והתנהגותיים.\n\n"
            f"{AI_DISCLOSURE}"
        ),
        "topic_ids":   [
            "psychotherapy",
            "behavioral_sciences",
            "cognition",
        ],
        "spotlight_routing": "therapy",
    },
    {
        "id":          "combined",
        "feed_file":   "feed.xml",
        "cover_file":  "cover.png",
        "title":       "סקירה שבועית בפסיכיאטריה",
        "description": (
            "סקירה שבועית בעברית של המאמרים המרכזיים בפסיכיאטריה, "
            "פסיכיאטריית הילד והמתבגר, התפתחות, נוירולוגיה, פסיכותרפיה "
            "וקוגניציה. מבוסס על PubMed ומופק אוטומטית מדי שבוע.\n\n"
            f"{AI_DISCLOSURE}"
        ),
        "topic_ids":   None,             # None = include every episode
        "spotlight_routing": "default",
    },
]


def get_channel_for_episode(topic_id: str, release_name: str = "") -> str:
    """Return the channel id ('child' / 'psychiatry' / 'therapy') that an
    episode belongs to. Used both for filtering and for the playlist note
    that appears in the combined feed's episode descriptions."""
    base = _topic_id_base(topic_id)
    # Regular cluster — match by topic_id
    for ch in CHANNELS:
        if ch["id"] == "combined":
            continue
        if ch["topic_ids"] and base in ch["topic_ids"]:
            return ch["id"]
    # Spotlight — match by keywords in the release name
    if base.startswith("spotlight_"):
        name_lower = release_name.lower()
        if any(kw.lower() in name_lower for kw in CHILD_PSYCH_KEYWORDS):
            return "child"
        if any(kw.lower() in name_lower for kw in THERAPY_KEYWORDS):
            return "therapy"
        return "psychiatry"
    return "psychiatry"  # safe default


def channel_for_id(channel_id: str) -> dict:
    for ch in CHANNELS:
        if ch["id"] == channel_id:
            return ch
    raise KeyError(f"Unknown channel id: {channel_id}")


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


def _extract_spotlight_title(rel_name_raw: str) -> str:
    """Pull the human-readable spotlight article title out of a release name
    like '📚 (10/12) מאמר סקירה: GBD 2023 ... — 2026-05-25'."""
    rel_name = rel_name_raw.replace("📚 ", "").strip()
    rel_name = EPISODE_NUM_RE.sub("", rel_name, count=1).strip()
    parts = rel_name.split(" — ")
    if len(parts) > 1:
        return " — ".join(parts[:-1]).strip()
    return rel_name or "מאמר סקירה מרכזי"


# Memoise articles.json loads — the same date may be looked up many times
# during one feed build (one episode per topic in the same week).
_ARTICLES_CACHE: dict[str, list[dict]] = {}


def _load_articles_for_date(date_str: str, repo_root: Path) -> list[dict]:
    """Read summaries/{date}/articles.json once and cache it.
    Returns [] if the file is missing (older weeks pre-articles.json)."""
    if date_str in _ARTICLES_CACHE:
        return _ARTICLES_CACHE[date_str]
    path = repo_root / "summaries" / date_str / "articles.json"
    if not path.exists():
        _ARTICLES_CACHE[date_str] = []
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            data = []
    except Exception:
        data = []
    _ARTICLES_CACHE[date_str] = data
    return data


def _articles_for_release(date_str: str, topic_id: str,
                           repo_root: Path) -> list[dict]:
    """Return the articles that this specific episode covered, sorted by
    Impact Factor (descending). Empty list if no metadata is available."""
    all_articles = _load_articles_for_date(date_str, repo_root)
    if not all_articles:
        return []
    # Exact match first — handles split topics ("psychotherapy_part2").
    matches = [a for a in all_articles if a.get("topic_id") == topic_id]
    if not matches:
        # Fall back to the cluster base id.
        base = topic_id.split("_part")[0]
        matches = [a for a in all_articles if a.get("topic_id") == base]
    matches.sort(key=lambda a: -float(a.get("impact_factor", 0) or 0))
    return matches


def _format_episode_description(
    articles: list[dict],
    cluster_label_he: str | None,
    playlist_he: str,
    label_en: str,
    date_str: str,
) -> str:
    """Build the per-episode <description> shown in the podcast app.

    Strategy: pull the actual paper list from articles.json so listeners
    see what's covered before they press play. Top 3 by Impact Factor get
    a bullet; the rest are summarised as a count. Falls back to a generic
    description when the metadata is unavailable (very old releases)."""
    lines: list[str] = []

    if articles:
        if len(articles) == 1:
            a = articles[0]
            t = a.get("title", "")
            if len(t) > 140:
                t = t[:140] + "…"
            j = a.get("journal", "")
            study = a.get("study_type_he") or ""
            extras = " · ".join(x for x in (j, study) if x)
            lines.append(f"פרק זה מוקדש למאמר אחד:")
            lines.append(f"• {t}")
            if extras:
                lines.append(f"  ({extras})")
        else:
            n = len(articles)
            lines.append(f"פרק זה כולל סקירה של {n} מאמרים, ביניהם:")
            for a in articles[:3]:
                t = a.get("title", "")
                if len(t) > 140:
                    t = t[:140] + "…"
                j = a.get("journal", "")
                study = a.get("study_type_he") or ""
                extras = " · ".join(x for x in (j, study) if x)
                if extras:
                    lines.append(f"• {t} ({extras})")
                else:
                    lines.append(f"• {t}")
            if n > 3:
                lines.append(f"ועוד {n - 3} מאמרים נוספים.")
    elif cluster_label_he:
        lines.append(f"סקירה שבועית של מאמרים מהקלאסטר: {cluster_label_he}.")

    lines.append("")
    if cluster_label_he:
        lines.append(f"קלאסטר: {cluster_label_he}")
    lines.append(f"סדרה: {playlist_he}")
    lines.append(f"תאריך הסקירה: {date_str}")
    lines.append("")
    lines.append(AI_DISCLOSURE)
    if label_en:
        lines.append("")
        lines.append(f"— {label_en} —")
    return "\n".join(lines)


def _extract_release_display_title(rel_name_raw: str) -> str:
    """Pull the actual display title out of a release name.

    Handles both the old format (📚 (3/12) ליבה — פסיכיאטריית ילד ומתבגר — DATE)
    and the new NotebookLM-titled format (📚 מדידת הנפש מהיער ועד לגלי המוח — DATE).
    Strips the book emoji, the (N/M) prefix, and the trailing "— YYYY-MM-DD"."""
    name = rel_name_raw.replace("📚 ", "").strip()
    name = EPISODE_NUM_RE.sub("", name, count=1).strip()
    parts = name.split(" — ")
    if len(parts) > 1:
        last = parts[-1].strip()
        # Strip the trailing segment only if it looks like a YYYY-MM-DD
        try:
            datetime.strptime(last, "%Y-%m-%d")
            return " — ".join(parts[:-1]).strip()
        except ValueError:
            pass
    return name.strip()


def build_feed(repo: str, channel: dict, releases: list[dict],
               out_dir: Path, pages_base: str) -> None:
    """Build the RSS feed for one channel and write it to out_dir/{feed_file}.

    `releases` is the full release list (fetched once and reused across the
    four feeds). Episodes are filtered to those whose channel matches.
    For the combined feed (channel["topic_ids"] is None) all episodes pass."""
    try:
        from feedgen.feed import FeedGenerator
    except ImportError:
        print("ERROR: feedgen not installed. pip install feedgen")
        sys.exit(2)

    out_path  = out_dir / channel["feed_file"]
    feed_url  = f"{pages_base}/{channel['feed_file']}"
    image_url = f"{pages_base}/{channel['cover_file']}"
    site_url  = f"https://github.com/{repo}"

    fg = FeedGenerator()
    fg.load_extension("podcast")
    fg.title(channel["title"])
    fg.link(href=site_url, rel="alternate")
    fg.link(href=feed_url, rel="self")
    fg.description(channel["description"])
    fg.language(PODCAST_LANGUAGE)
    fg.author({"name": PODCAST_AUTHOR, "email": PODCAST_EMAIL})
    fg.podcast.itunes_author(PODCAST_AUTHOR)
    fg.podcast.itunes_summary(channel["description"])
    fg.podcast.itunes_owner(name=PODCAST_AUTHOR, email=PODCAST_EMAIL)
    fg.podcast.itunes_explicit("no")
    fg.podcast.itunes_category(PODCAST_CATEGORY, PODCAST_SUBCATEGORY)
    fg.podcast.itunes_type("episodic")
    fg.podcast.itunes_image(image_url)
    fg.image(image_url, channel["title"], site_url)

    is_combined = channel["topic_ids"] is None
    repo_root   = Path(__file__).resolve().parent.parent

    episodes = 0
    for rel in releases:
        tag = rel.get("tag_name", "")
        parsed = _parse_tag(tag)
        if not parsed:
            continue
        date_str, topic_id = parsed
        rel_name_raw = rel.get("name", "")

        # Resolve cluster labels (used for topic_desc + label_en orientation)
        labels = TOPIC_LABELS.get(_topic_id_base(topic_id))
        if not labels:
            if topic_id.startswith("spotlight_"):
                labels = (
                    None,  # display title comes from release name
                    "Spotlight Review",
                    "פודקאסט ייעודי על מאמר סקירה מרכזי מהשבוע — "
                    "סקירה ארוכה ומעמיקה של מאמר בודד.",
                )
            else:
                continue
        cluster_label_he, label_en, topic_desc = labels

        # Channel filtering — skip episodes that don't belong to this channel
        episode_channel = get_channel_for_episode(topic_id, rel_name_raw)
        if not is_combined and episode_channel != channel["id"]:
            continue

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

        # Display title comes from the release name itself — this is either
        # the NotebookLM-generated title (newer releases) or the old cluster
        # label (releases from before the NotebookLM-title capture landed).
        # Either way, parsing the release name uses what's actually there.
        display_title = _extract_release_display_title(rel_name_raw)
        if not display_title:
            # Truly empty? Fall back to cluster label.
            display_title = cluster_label_he or "פרק"

        playlist_he = {
            "child":      "פסיכיאטריית הילד והמתבגר",
            "psychiatry": "פסיכיאטריה ומדעי המוח",
            "therapy":    "פסיכותרפיה וקוגניציה",
        }[episode_channel]

        # In dedicated channel feeds — clean title.
        # In the combined feed — append the playlist tag so listeners
        # browsing the combined feed know which series each episode came from.
        if is_combined:
            title = f"{display_title} | {playlist_he} — {date_str}"
        else:
            title = f"{display_title} — {date_str}"

        # Build the description from the actual paper list (top 3 by IF +
        # count of the rest). Falls back to generic text when articles.json
        # isn't available for very old releases.
        articles = _articles_for_release(date_str, topic_id, repo_root)
        description = _format_episode_description(
            articles, cluster_label_he, playlist_he, label_en, date_str,
        )

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
        # Combined feed keeps iTunes seasons (1-9) for backwards compat with
        # any listener using the season filter on the old subscription.
        if is_combined:
            fe.podcast.itunes_season(get_playlist_number(topic_id, rel_name_raw))
        episodes += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fg.rss_file(str(out_path), pretty=True)
    print(f"  {channel['id']:11s} → {out_path.name}  ({episodes} episode(s))")


def main() -> int:
    repo = _resolve_repo()
    out_dir = Path(__file__).resolve().parent.parent / "docs"
    pages_base = os.environ.get("PAGES_BASE_URL", DEFAULT_PAGES_BASE)

    print(f"Fetching releases from {repo}...")
    releases = _fetch_releases(repo)
    print(f"  Found {len(releases)} release(s).\n")

    print("Building feeds:")
    for channel in CHANNELS:
        build_feed(repo, channel, releases, out_dir, pages_base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
