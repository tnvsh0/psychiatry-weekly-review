#!/usr/bin/env python3
"""
One-shot rescue for the 2 spotlight podcasts that failed to start during
the 2026-05-25 run due to NotebookLM rate-limiting on `generate audio`
(after 10 successful concurrent starts, the 11th and 12th got "FAILED to
start" with empty stderr).

This script:
  1. Triggers audio generation in the 2 already-created notebooks
     (sources are already uploaded, so generation is one call away).
  2. Waits for both to finish (parallel on Google's side).
  3. Downloads the MP3s.
  4. Uploads to GitHub Releases with the matching tag + episode number
     so they appear correctly in the RSS feed.

Designed to run on the VM where the NotebookLM session is valid.
Imports TONE_GUIDANCE from the main script so prompts match exactly.

Usage (on VM):
    cd /opt/psychiatry-weekly-review
    export GH_TOKEN=$(gcloud secrets versions access latest \
        --secret=github-token --project=psych-research-agent)
    export GH_REPO=tnvsh0/psychiatry-weekly-review
    sudo -u User -E env PATH=/opt/venv/bin:$PATH GH_TOKEN=$GH_TOKEN \
        GH_REPO=$GH_REPO /opt/venv/bin/python scripts/rescue_spotlights.py
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Import TONE_GUIDANCE so the rescue prompts match the rest of the pipeline
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from weekly_review import TONE_GUIDANCE  # noqa: E402

DATE_STR = "2026-05-25"
EPISODE_TOTAL = 12

# Article metadata captured from the original run's log (2026-05-25). Both
# are review articles in Lancet Psychiatry (IF 64.3) that failed at start.
MISSING_SPOTLIGHTS = [
    {
        "nb_id":         "ceb2ee6e-cdea-41fe-8941-2a3159752102",
        "pmid":          "42134365",
        "title":         "Pharmacological interventions for ADHD: a systematic review and dose-effect meta-analysis",
        "authors":       "Nourredine M et al.",
        "journal":       "Lancet Psychiatry",
        "impact_factor": 64.3,
        "episode_num":   11,
        "topic_id":      "spotlight_42134365",
        "label_he":      "מאמר סקירה: Nourredine M — Pharmacological interventions for ADHD: a systemat…",
        "label_en":      "Spotlight: Nourredine M — Pharmacological interventions for ADHD",
    },
    {
        "nb_id":         "383cd230-0238-4875-bb2c-ead433c5d68e",
        "pmid":          "42134364",
        "title":         "Maternal and paternal antidepressant use before and during pregnancy and offspring outcomes",
        "authors":       "Chan JKN et al.",
        "journal":       "Lancet Psychiatry",
        "impact_factor": 64.3,
        "episode_num":   12,
        "topic_id":      "spotlight_42134364",
        "label_he":      "מאמר סקירה: Chan JKN — Maternal and paternal antidepressant use before an…",
        "label_en":      "Spotlight: Chan JKN — Maternal and paternal antidepressant use during pregnancy",
    },
]


def build_spotlight_prompt(s: dict) -> str:
    """Mirror the spotlight prompt from weekly_review.py.find_spotlight_reviews."""
    base = (
        f"This is a DEDICATED, single-paper deep-dive podcast on one "
        f"high-impact review article:\n"
        f"  Title: \"{s['title']}\"\n"
        f"  Authors: {s['authors']}\n"
        f"  Journal: {s['journal']} (IF: {s['impact_factor']:.1f})\n"
        f"  Type: review / systematic review / meta-analysis\n\n"
        "Treat this as a LONG, comprehensive single-paper podcast — "
        "every section of the review deserves real discussion. "
        "Cover: (a) the clinical or scientific question motivating the "
        "review, (b) the methodology (for a systematic review: search "
        "strategy, inclusion criteria, risk-of-bias assessment, "
        "heterogeneity I², publication bias; for a narrative review: "
        "the author's framework and how they structure the evidence), "
        "(c) the synthesis of evidence with effect sizes and confidence "
        "intervals where given, (d) controversies and counter-arguments, "
        "(e) limitations of the evidence base, (f) clinical implications "
        "for everyday practice. "
        "If this is a Stahl-style psychopharmacology review: name the "
        "receptors, mechanisms, pharmacokinetics, and clinical pearls "
        "carefully — that level of mechanistic detail is what makes "
        "Stahl reviews valuable. "
        "For a child / adolescent psychiatry resident: emphasize what "
        "should change in clinical practice, what remains uncertain, "
        "what to do differently tomorrow morning. "
        "Generate the podcast entirely in Hebrew."
    )
    return base + TONE_GUIDANCE


def start_podcast(nb_id: str, prompt: str, env: dict) -> str | None:
    subprocess.run(
        ["notebooklm", "use", nb_id],
        capture_output=True, env=env, timeout=30,
    )
    try:
        out = subprocess.run([
            "notebooklm", "generate", "audio", prompt,
            "--format", "deep-dive", "--length", "long",
            "--language", "he", "--json",
        ], capture_output=True, text=True, env=env, timeout=120)
        raw = out.stdout.strip()
        if not raw:
            print(f"    ERROR start_podcast: empty output. stderr: {out.stderr[:300]}")
            return None
        data = json.loads(raw)
        return data.get("task_id") or None
    except Exception as e:
        print(f"    ERROR start_podcast: {e}")
        return None


def wait_for_artifacts(spotlights: list[dict], env: dict, max_wait: int = 4500):
    pending = {
        s["nb_id"]: s for s in spotlights if s.get("task_id")
    }
    if not pending:
        print("  Nothing to wait for.")
        return

    print(f"\nWaiting for {len(pending)} podcast(s)...")
    start = time.time()
    while pending and time.time() - start < max_wait:
        time.sleep(60)
        elapsed_min = int((time.time() - start) / 60)
        for nb_id in list(pending.keys()):
            s = pending[nb_id]
            subprocess.run(
                ["notebooklm", "use", nb_id],
                capture_output=True, env=env, timeout=30,
            )
            try:
                out = subprocess.run(
                    ["notebooklm", "artifact", "list", "--json"],
                    capture_output=True, text=True, env=env, timeout=30,
                )
                artifacts = json.loads(out.stdout).get("artifacts", [])
                for a in artifacts:
                    if a.get("id") == s["task_id"]:
                        status = a.get("status", "unknown")
                        print(f"  [{elapsed_min}m] {s['pmid']}: {status}")
                        if status == "completed":
                            s["ready"] = True
                            del pending[nb_id]
                        elif status in ("failed", "unknown"):
                            print(f"  ERROR: {s['pmid']} failed")
                            del pending[nb_id]
            except Exception as e:
                print(f"  Polling error for {nb_id}: {e}")

    if pending:
        print(f"  WARNING: Timed out on: {[s['pmid'] for s in pending.values()]}")


def download_and_upload(s: dict, env: dict) -> bool:
    """Download MP3 and upload to GitHub Releases with proper title."""
    podcast_dir = Path("podcasts") / DATE_STR
    podcast_dir.mkdir(parents=True, exist_ok=True)
    path = podcast_dir / f"{s['topic_id']}.mp3"

    subprocess.run(
        ["notebooklm", "use", s["nb_id"]],
        capture_output=True, env=env, timeout=30,
    )
    result = subprocess.run(
        ["notebooklm", "download", "audio", str(path), "-a", s["task_id"]],
        capture_output=True, text=True, env=env, timeout=300,
    )
    if result.returncode != 0 or not path.exists() or path.stat().st_size < 100_000:
        print(f"  Download failed for {s['pmid']}: {result.stderr[:200]}")
        return False
    size_mb = path.stat().st_size / (1024 * 1024)
    print(f"  Downloaded {s['topic_id']}: {size_mb:.1f} MB")

    repo = env.get("GH_REPO") or env.get("GITHUB_REPOSITORY") or "tnvsh0/psychiatry-weekly-review"
    tag = f"weekly-{DATE_STR}-{s['topic_id']}"
    title_prefix = f"({s['episode_num']}/{EPISODE_TOTAL}) "
    title = f"\U0001f4da {title_prefix}{s['label_he']} — {DATE_STR}"
    notes = (
        f"{s['label_en']} — rescued after rate-limiting failure on the "
        f"original {DATE_STR} run.\n\n*Generated automatically*"
    )
    up = subprocess.run([
        "gh", "release", "create", tag, str(path),
        "--title", title,
        "--notes", notes,
        "--repo", repo,
    ], capture_output=True, text=True, env=env, timeout=180)
    if up.returncode != 0:
        print(f"  Upload failed for {s['topic_id']}: {up.stderr[:300]}")
        return False
    print(f"  Uploaded {s['topic_id']} as {tag}")
    return True


def main() -> int:
    env = os.environ.copy()
    print("=" * 70)
    print(f"Rescuing 2 missing spotlight podcasts from {DATE_STR}")
    print("=" * 70)

    # Phase 1: start both audio generations with a longer pause between
    # them to dodge the rate limit that bit the original run.
    print("\nStarting audio generation...")
    for i, s in enumerate(MISSING_SPOTLIGHTS):
        prompt = build_spotlight_prompt(s)
        task_id = start_podcast(s["nb_id"], prompt, env)
        s["task_id"] = task_id
        print(f"  {s['pmid']}: task_id={task_id or 'FAILED'}")
        if i < len(MISSING_SPOTLIGHTS) - 1:
            # 30s gap between starts (vs the 10s the main script used).
            time.sleep(30)

    started = [s for s in MISSING_SPOTLIGHTS if s.get("task_id")]
    if not started:
        print("\nERROR: No generations started.")
        return 1

    # Phase 2: wait
    wait_for_artifacts(MISSING_SPOTLIGHTS, env)

    # Phase 3: download + upload each successful one
    print("\nDownloading + uploading completed podcasts...")
    success = 0
    for s in MISSING_SPOTLIGHTS:
        if not s.get("ready"):
            print(f"  Skipping {s['pmid']} (not ready)")
            continue
        if download_and_upload(s, env):
            success += 1

    print(f"\n{'=' * 70}")
    print(f"Rescue summary: {success}/{len(MISSING_SPOTLIGHTS)} podcasts recovered.")
    print(f"{'=' * 70}")
    return 0 if success == len(MISSING_SPOTLIGHTS) else 1


if __name__ == "__main__":
    sys.exit(main())
