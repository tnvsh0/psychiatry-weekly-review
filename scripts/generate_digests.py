#!/usr/bin/env python3
"""
Weekly text digests generated from the same PubMed abstracts the podcasts use.

Two deliverables, written into summaries/<date>/ so they are committed to the
repo and browsable on GitHub next to the audio:

  1. Take-home messages (one file per REVIEW channel):
       summaries/<date>/takehome-<channel>.md
     For every article in that channel this week: a short Hebrew summary plus a
     bolded **מסר מרכזי (Take-home)** — the one-line clinical bottom line.

  2. Clinical questions for the encounter (one file for the whole week):
       summaries/<date>/clinical-questions.md
     Concrete questions a child/adolescent psychiatrist could ask patients,
     GROUNDED in this week's findings (e.g. an article on nutrition → questions
     to ask about diet), grouped by theme.

Both are produced by a single LLM call each (Google Gemini), reading ONLY the
abstracts we already fetched — the model is told not to invent anything.

Requires:
    GEMINI_API_KEY      — (or GOOGLE_API_KEY) if unset, or the `google-genai`
                          package is missing, the whole step is skipped with a
                          warning (non-fatal), like the optional Drive backup.
Optional:
    DIGEST_MODEL        — Gemini model id (default: gemini-2.5-flash).

Usage:
    python scripts/generate_digests.py --date 2026-07-05
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Reuse the channel routing + names from the RSS builder so digests and feeds
# always agree on which cluster belongs to which channel.
from generate_rss import get_channels_for_episode, PLAYLIST_HE_BY_CHANNEL  # noqa: E402

DEFAULT_MODEL = os.environ.get("DIGEST_MODEL", "gemini-2.5-flash")

# The 3 review channels digests are produced for (spotlight channels excluded —
# a spotlight already gets a full deep-dive episode).
REVIEW_CHANNELS = ["child", "psychiatry", "therapy"]

AI_DISCLOSURE = (
    "> ⚠️ נוצר אוטומטית באמצעות בינה מלאכותית על בסיס תקצירי המאמרים בלבד. "
    "עלול להכיל אי-דיוקים — יש לאמת כל פרט מול המאמר המקורי לפני הסתמכות קלינית."
)


# ── Gemini client (lazy, graceful) ────────────────────────────────────────────
def _gemini(system: str, user: str, model: str, max_tokens: int = 4096) -> str | None:
    """Single Gemini completion. Returns text, or None if unavailable/failed."""
    key = (os.environ.get("GEMINI_API_KEY")
           or os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not key:
        print("  Digests skipped: GEMINI_API_KEY not set.")
        return None
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("  Digests skipped: `google-genai` not installed "
              "(pip install google-genai).")
        return None
    try:
        client = genai.Client(api_key=key)
        resp = client.models.generate_content(
            model=model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                # Gemini 2.5 counts "thinking" tokens toward max_output_tokens.
                # Digests need lots of OUTPUT (a per-article summary for a busy
                # channel can be 50+ articles), so keep thinking small and give
                # the output plenty of room, or the file gets truncated.
                thinking_config=types.ThinkingConfig(thinking_budget=512),
                max_output_tokens=max_tokens,
                temperature=0.4,
            ),
        )
        return (resp.text or "").strip() or None
    except Exception as e:
        print(f"  WARNING: Gemini call failed: {e}")
        return None


# ── Data loading ──────────────────────────────────────────────────────────────
def _load_articles(date_str: str) -> list[dict]:
    path = REPO_ROOT / "summaries" / date_str / "articles.json"
    if not path.exists():
        print(f"  No articles.json for {date_str} — nothing to digest.")
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"  WARNING: could not read {path}: {e}")
        return []


def _review_channel_of(topic_id: str) -> str | None:
    """Return the review-channel id for a cluster topic, or None for spotlights
    / anything that doesn't map to one of the 3 review channels."""
    if str(topic_id).startswith("spotlight_"):
        return None
    chans = get_channels_for_episode(topic_id)
    for c in chans:
        if c in REVIEW_CHANNELS:
            return c
    return None


def _article_block(a: dict, abstract_chars: int = 1500) -> str:
    """Compact per-article text handed to the model."""
    abstract = (a.get("abstract") or "").strip()
    if len(abstract) > abstract_chars:
        abstract = abstract[:abstract_chars] + "…"
    return (
        f"### {a.get('title', '').strip()}\n"
        f"- כתב עת: {a.get('journal', '')}\n"
        f"- סוג מחקר: {a.get('study_type_he', '')}\n"
        f"- מחברים: {a.get('authors', '')}\n"
        f"- קישור: {a.get('url', '')}\n"
        f"- תקציר: {abstract or '(אין תקציר)'}\n"
    )


# ── Take-home digest (item 7) ─────────────────────────────────────────────────
TAKEHOME_SYSTEM = (
    "You are a medical editor writing a Hebrew clinical digest for a "
    "child-and-adolescent-psychiatry resident. You summarise research papers "
    "faithfully and concisely. You NEVER invent findings, numbers, or "
    "conclusions that are not in the provided abstract. If an abstract is "
    "missing, say so briefly rather than guessing. Output valid Markdown in "
    "Hebrew."
)


def _takehome_prompt(channel_he: str, articles: list[dict]) -> str:
    blocks = "\n".join(_article_block(a) for a in articles)
    return (
        f"להלן מאמרי הסקירה השבועית בתחום \"{channel_he}\". "
        f"עבור כל מאמר, כתוב בעברית:\n"
        f"1. כותרת מודגשת של המאמר (אפשר לתרגם לעברית, עם השם המקורי בסוגריים), "
        f"ובשורה מתחת: שם כתב העת וסוג המחקר.\n"
        f"2. סיכום של 2–4 משפטים — השאלה, השיטה בקצרה, והממצא המרכזי עם מספרים "
        f"אם הופיעו בתקציר.\n"
        f"3. שורה שמתחילה ב-**מסר מרכזי (Take-home):** ואחריה משפט אחד — "
        f"השורה התחתונה הקלינית למתמחה.\n\n"
        f"הקפד: הסתמך אך ורק על התקצירים שלהלן, אל תמציא ממצאים. שמור על טון "
        f"מדוד (בלי מילים כמו 'פורץ דרך'). הפרד בין מאמרים בקו אופקי (---).\n\n"
        f"המאמרים:\n\n{blocks}"
    )


def build_takehome(date_str: str, channel_id: str, articles: list[dict],
                   model: str) -> bool:
    channel_he = PLAYLIST_HE_BY_CHANNEL.get(channel_id, channel_id)
    body = _gemini(
        TAKEHOME_SYSTEM,
        _takehome_prompt(channel_he, articles),
        model,
        max_tokens=16384,
    )
    if not body:
        return False
    out = (
        f"# 📌 מסרים מרכזיים — {channel_he}\n"
        f"### סקירה שבועית — {date_str}\n\n"
        f"{AI_DISCLOSURE}\n\n"
        f"**מספר מאמרים:** {len(articles)}\n\n"
        f"---\n\n"
        f"{body}\n"
    )
    path = REPO_ROOT / "summaries" / date_str / f"takehome-{channel_id}.md"
    path.write_text(out, encoding="utf-8")
    print(f"  Wrote {path.relative_to(REPO_ROOT)}  ({len(articles)} articles)")
    return True


# ── Clinical questions (item 8) ───────────────────────────────────────────────
QUESTIONS_SYSTEM = (
    "You are a senior child-and-adolescent psychiatrist mentoring a resident. "
    "From recent research you derive PRACTICAL questions the clinician can ask "
    "patients (or parents) in the room. Every question must be grounded in a "
    "specific finding from the provided abstracts — no generic intake "
    "questions, no invented evidence. Output valid Markdown in Hebrew."
)


def _questions_prompt(articles: list[dict]) -> str:
    blocks = "\n".join(_article_block(a, abstract_chars=1000) for a in articles)
    return (
        "על בסיס ממצאי המאמרים שלהלן מהשבוע, הצע שאלות קונקרטיות שרופא/ה "
        "בפסיכיאטריה של הילד והמתבגר יכול/ה לשאול מטופלים או הורים בקליניקה — "
        "שאלות שנובעות ישירות מממצא במאמר. לדוגמה: אם מאמר מצא קשר בין תזונה "
        "לתסמינים, הצע שאלות לבירור הרגלי תזונה.\n\n"
        "ארגן לפי נושאים (כותרת לכל נושא). תחת כל נושא: 2–5 שאלות במשפטים "
        "שלמים, וציין בסוגריים בקצרה מאיזה ממצא/מאמר השאלה נובעת. הצע רק שאלות "
        "שמעוגנות בממצאים שלהלן; אל תמציא. שמור על טון מקצועי ומדוד.\n\n"
        f"המאמרים:\n\n{blocks}"
    )


def build_questions(date_str: str, articles: list[dict], model: str) -> bool:
    body = _gemini(
        QUESTIONS_SYSTEM,
        _questions_prompt(articles),
        model,
        max_tokens=16384,
    )
    if not body:
        return False
    out = (
        f"# 💬 שאלות לקליניקה — מבוסס על מחקרי השבוע\n"
        f"### סקירה שבועית — {date_str}\n\n"
        f"{AI_DISCLOSURE}\n\n"
        f"> רעיונות לשאלות שנגזרות מהמאמרים השבוע — לא תחליף לשיקול דעת קליני.\n\n"
        f"---\n\n"
        f"{body}\n"
    )
    path = REPO_ROOT / "summaries" / date_str / "clinical-questions.md"
    path.write_text(out, encoding="utf-8")
    print(f"  Wrote {path.relative_to(REPO_ROOT)}  "
          f"(from {len(articles)} articles)")
    return True


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="Weekly take-home + clinical-question digests.")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD run date")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="Claude model id")
    args = ap.parse_args()

    print(f"\n📝 Generating weekly digests for {args.date} (model={args.model})...")
    articles = _load_articles(args.date)
    if not articles:
        return 0

    # Group review-cluster articles by channel (spotlights excluded).
    by_channel: dict[str, list[dict]] = {c: [] for c in REVIEW_CHANNELS}
    review_articles: list[dict] = []
    for a in articles:
        ch = _review_channel_of(a.get("topic_id", ""))
        if ch:
            by_channel[ch].append(a)
            review_articles.append(a)

    if not review_articles:
        print("  No review-channel articles to digest (spotlights-only run?).")
        return 0

    # Item 7 — one take-home file per channel.
    any_ok = False
    for ch in REVIEW_CHANNELS:
        arts = by_channel[ch]
        if not arts:
            continue
        if build_takehome(args.date, ch, arts, args.model):
            any_ok = True

    # Item 8 — one clinical-questions file for the whole week.
    if build_questions(args.date, review_articles, args.model):
        any_ok = True

    if not any_ok:
        print("  No digests produced (LLM unavailable).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
