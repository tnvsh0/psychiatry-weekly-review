#!/usr/bin/env python3
"""
Quality-control evaluator ("the loop's judge") for the weekly podcasts.

This is an EVALUATOR, not an optimizer: it measures each episode and writes a
report for a human to act on. It does NOT auto-tune the prompt or regenerate —
NotebookLM is a black box with non-deterministic output, so a closed
self-optimizing loop would chase noise. Instead we surface problems so the
user can decide whether to re-run an episode or adjust the prompt.

It uses ONE model — Google Gemini — which is natively multimodal: we hand it
the episode's MP3 directly (via the Files API) together with the SOURCE
abstracts and ask it to listen and score the episode. No separate speech-to-text
step, no ffmpeg, no 25 MB limit.

Per episode Gemini scores:
    • accuracy  — does the podcast faithfully represent the abstracts?
                  (hallucinations, invented numbers, misstated findings)
    • coverage  — were the source papers actually discussed?
    • fluency   — complete sentences vs the "jumps"/cut-offs; consistent host
                  genders; real two-host dialogue.
Results aggregate into summaries/<date>/qc-report.md plus an ntfy summary.

Requires (optional — missing → graceful skip):
    GEMINI_API_KEY   (or GOOGLE_API_KEY). Without it, QC is skipped.
Optional:
    QC_MODEL         Gemini model id (default: gemini-2.5-flash; use
                     gemini-2.5-pro for a stricter judge).
    NTFY_TOPIC       push a one-line QC summary when set.

Usage:
    python scripts/qc_review.py --date 2026-07-05 [--limit N]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = os.environ.get("QC_MODEL", "gemini-2.5-flash")


# ── Gemini audio judge ────────────────────────────────────────────────────────
JUDGE_SYSTEM = (
    "You are a meticulous medical-education QC reviewer. You are given (A) the "
    "SOURCE abstracts a Hebrew podcast episode was built from, and (B) the "
    "AUDIO of that episode. Listen to the audio and judge how faithful and how "
    "well-made the episode is. Be strict about factual accuracy: flag any "
    "claim, number, or conclusion in the audio that is not supported by the "
    "source, and any source paper that was not actually discussed. Judge ONLY "
    "against the provided source; do not use outside knowledge. Reply with ONLY "
    "a JSON object."
)

JUDGE_INSTRUCTIONS = (
    "Return a JSON object with EXACTLY these keys:\n"
    '  "accuracy": integer 1-5 (5 = every claim traceable to the source),\n'
    '  "coverage": integer 1-5 (5 = all source papers discussed),\n'
    '  "fluency": integer 1-5 (5 = complete sentences, no cut-offs/"jumps", '
    'consistent host genders, real two-host dialogue),\n'
    '  "hallucinations": array of short Hebrew strings (claims not supported by '
    'the source; [] if none),\n'
    '  "missed_papers": array of short Hebrew strings (source papers not '
    'discussed; [] if none),\n'
    '  "notes": array of short Hebrew strings (other quality issues, e.g. '
    'cut-off sentences, gender flips),\n'
    '  "verdict": one of "ok", "review", "problem".'
)


def _gemini_client():
    key = (os.environ.get("GEMINI_API_KEY")
           or os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not key:
        print("QC skipped: GEMINI_API_KEY not set.")
        return None, None
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("QC skipped: `google-genai` not installed (pip install google-genai).")
        return None, None
    try:
        return genai.Client(api_key=key), types
    except Exception as e:
        print(f"QC skipped: could not init Gemini client: {e}")
        return None, None


def judge_episode(client, types, mp3: Path, source_md: str, model: str) -> dict | None:
    """Upload the MP3, ask Gemini to listen + score against the source. Returns
    the parsed verdict dict, or None on failure."""
    myfile = None
    try:
        myfile = client.files.upload(file=str(mp3))
        # Large audio may need a moment to process before it can be used.
        for _ in range(30):
            state = getattr(getattr(myfile, "state", None), "name", "ACTIVE")
            if state == "ACTIVE":
                break
            if state == "FAILED":
                print(f"    {mp3.name}: file processing FAILED.")
                return None
            time.sleep(2)
            myfile = client.files.get(name=myfile.name)

        prompt = (
            f"{JUDGE_INSTRUCTIONS}\n\n=== SOURCE ABSTRACTS ===\n{source_md[:18000]}"
        )
        resp = client.models.generate_content(
            model=model,
            contents=[myfile, prompt],
            config=types.GenerateContentConfig(
                system_instruction=JUDGE_SYSTEM,
                response_mime_type="application/json",
                # Gemini 2.5 "thinking" tokens count toward max_output_tokens,
                # so budget for both: a bounded amount of reasoning plus the
                # (small) JSON verdict. Too low a cap → the reply gets cut off
                # mid-thought and no JSON comes back.
                thinking_config=types.ThinkingConfig(thinking_budget=2048),
                max_output_tokens=6144,
                temperature=0.2,
            ),
        )
        text = (resp.text or "").strip()
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            return None
        return json.loads(text[start:end + 1])
    except Exception as e:
        print(f"    Judge failed for {mp3.name}: {e}")
        return None
    finally:
        if myfile is not None:
            try:
                client.files.delete(name=myfile.name)
            except Exception:
                pass


# ── Report ────────────────────────────────────────────────────────────────────
def _verdict_icon(v: str) -> str:
    return {"ok": "✅", "review": "🟡", "problem": "🔴"}.get(v, "⚪")


def _load_titles(date_str: str) -> dict[str, str]:
    """topic_id → a readable title, from articles.json (Hebrew label)."""
    path = REPO_ROOT / "summaries" / date_str / "articles.json"
    titles: dict[str, str] = {}
    if path.exists():
        try:
            for a in json.loads(path.read_text(encoding="utf-8")):
                tid = a.get("topic_id", "")
                if tid and tid not in titles:
                    titles[tid] = a.get("topic_he", tid)
        except Exception:
            pass
    return titles


def main() -> int:
    ap = argparse.ArgumentParser(description="Weekly podcast QC evaluator (Gemini).")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD run date")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="Gemini judge model")
    ap.add_argument("--limit", type=int, default=0,
                    help="QC only the first N episodes (0 = all)")
    args = ap.parse_args()

    client, types = _gemini_client()
    if client is None:
        return 0

    pod_dir = REPO_ROOT / "podcasts" / args.date
    sum_dir = REPO_ROOT / "summaries" / args.date
    mp3s = sorted(pod_dir.glob("*.mp3")) if pod_dir.exists() else []
    if args.limit > 0:
        mp3s = mp3s[:args.limit]
    if not mp3s:
        print(f"QC: no MP3s in {pod_dir} — nothing to review.")
        return 0

    print(f"\n🔎 QC review for {args.date}: {len(mp3s)} episode(s) (model={args.model})...")
    titles = _load_titles(args.date)
    results: list[dict] = []

    for mp3 in mp3s:
        topic_id = mp3.stem
        src_path = sum_dir / f"{topic_id}.md"
        if not src_path.exists():
            print(f"  {topic_id}: no source md — skipping.")
            continue
        print(f"  {topic_id}: uploading + judging...")
        verdict = judge_episode(
            client, types, mp3, src_path.read_text(encoding="utf-8"), args.model,
        )
        if not verdict:
            print(f"  {topic_id}: no verdict — skipping.")
            continue
        verdict["topic_id"] = topic_id
        verdict["title"] = titles.get(topic_id, topic_id)
        results.append(verdict)
        print(f"    → {verdict.get('verdict')} "
              f"(acc {verdict.get('accuracy')}, cov {verdict.get('coverage')}, "
              f"flu {verdict.get('fluency')})")

    if not results:
        print("QC: no episodes evaluated.")
        return 0

    _write_report(args.date, results)
    _notify(args.date, results)
    return 0


def _write_report(date_str: str, results: list[dict]) -> None:
    lines = [
        f"# 🔎 דו\"ח בקרת איכות — {date_str}",
        "",
        "> נוצר אוטומטית: Gemini מאזין לכל פרק ומשווה מול תקצירי המקור. "
        "ציונים 1–5. זהו כלי סינון — אין להסתמך עליו כאמת מוחלטת.",
        "",
        "| פרק | דיוק | כיסוי | שטף | סיכום |",
        "|-----|:----:|:-----:|:---:|-------|",
    ]
    for r in sorted(results, key=lambda x: (x.get("accuracy", 5), x.get("coverage", 5))):
        lines.append(
            f"| {_verdict_icon(r.get('verdict',''))} {r.get('title', r['topic_id'])} "
            f"| {r.get('accuracy','?')} | {r.get('coverage','?')} "
            f"| {r.get('fluency','?')} | {r.get('verdict','')} |"
        )
    lines.append("")
    flagged = [r for r in results if r.get("verdict") != "ok"
               or r.get("hallucinations") or r.get("missed_papers")]
    if flagged:
        lines += ["---", "", "## פירוט לפרקים שסומנו", ""]
        for r in flagged:
            lines.append(f"### {_verdict_icon(r.get('verdict',''))} {r.get('title', r['topic_id'])}")
            for label, key in (("הזיות/אי-דיוקים", "hallucinations"),
                               ("מאמרים שדולגו", "missed_papers"),
                               ("הערות איכות", "notes")):
                items = r.get(key) or []
                if items:
                    lines.append(f"**{label}:**")
                    lines += [f"- {it}" for it in items]
                    lines.append("")
            lines.append("")
    out = REPO_ROOT / "summaries" / date_str / "qc-report.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Wrote {out.relative_to(REPO_ROOT)}")


def _notify(date_str: str, results: list[dict]) -> None:
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        return
    n = len(results)
    probs = sum(1 for r in results if r.get("verdict") == "problem")
    revs = sum(1 for r in results if r.get("verdict") == "review")
    avg_acc = sum(r.get("accuracy", 0) for r in results) / n if n else 0
    msg = (f"נבדקו {n} פרקים · דיוק ממוצע {avg_acc:.1f}/5 · "
           f"🔴 {probs} · 🟡 {revs}")
    try:
        requests.post("https://ntfy.sh", json={
            "topic": topic,
            "title": f"🔎 בקרת איכות — {date_str}",
            "message": msg,
            "priority": 4 if probs else 3,
            "tags": ["mag"],
        }, timeout=15)
    except Exception as e:
        print(f"  ntfy failed: {e}")


if __name__ == "__main__":
    sys.exit(main())
