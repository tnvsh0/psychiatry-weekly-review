#!/usr/bin/env python3
"""
Judge episodes that were published WITHOUT a verdict, and pull back the ones
that should never have gone out.

The pipeline fails open on purpose: no Gemini key, or a judge that errors, and
the episode publishes anyway. That is the right trade — episodes without a
score beat no episodes. But it leaves a hole, and on 2026-08-31 the hole was
the whole run: the Gemini project hit its monthly spending cap, all 18 judge
calls returned 429, and 18 episodes reached Spotify with no quality check at
all. Nothing existed to go back and check them afterwards.

This does. It needs no NotebookLM generation: the audio is already on the
release, so it downloads what was published, runs the ordinary judge over it,
and applies the ordinary gate. An episode that fails is converted back to a
DRAFT — out of the feed, its notebook untouched — which is exactly where the
gate would have put it had the judge been reachable at the time.

    python scripts/qc_published.py --date 2026-08-31 --dry-run
    python scripts/qc_published.py --date 2026-08-31
    python scripts/qc_published.py --date 2026-08-31 --judge-only   # score, don't unpublish

Re-runnable: episodes that already carry a verdict in qc-results.json are
skipped unless --force is given.

Run on the VM (needs `gh` and GEMINI_API_KEY).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import weekly_review as w  # noqa: E402


def _repo() -> str:
    repo = os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        print("ERROR: GH_REPO not set."); sys.exit(1)
    return repo


def _published_tags(repo: str, date_str: str) -> list[str]:
    """Non-draft releases for this date. A draft is already out of the feed."""
    out = subprocess.run(
        ["gh", "api", f"repos/{repo}/releases?per_page=100", "--paginate",
         "--jq", ".[]|select(.draft|not)|.tag_name"],
        capture_output=True, text=True, timeout=120,
    )
    marker = f"weekly-{date_str}-"
    return sorted(ln.strip() for ln in out.stdout.splitlines() if marker in ln)


def _existing_verdicts(date_str: str) -> dict:
    p = REPO_ROOT / "summaries" / date_str / "qc-results.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", required=True, help="YYYY-MM-DD run date")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="re-judge episodes that already have a verdict")
    ap.add_argument("--judge-only", action="store_true",
                    help="write verdicts but do not unpublish anything")
    args = ap.parse_args()

    repo = _repo()
    env = os.environ.copy()
    if not (env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")):
        print("ERROR: no GEMINI_API_KEY — the judge cannot run."); return 1

    tags = _published_tags(repo, args.date)
    if not tags:
        print(f"No published releases for {args.date}."); return 0

    have = _existing_verdicts(args.date)
    marker = f"weekly-{args.date}-"
    todo = [t for t in tags
            if args.force or not (have.get(t.split(marker, 1)[1]) or {}).get("accuracy")]

    print(f"{args.date}: {len(tags)} published, {len(tags) - len(todo)} already "
          f"judged, {len(todo)} to judge")
    for t in todo:
        print(f"  - {t.split(marker, 1)[1]}")
    if args.dry_run:
        print("\n(dry run — nothing downloaded, judged or unpublished)")
        return 0
    if not todo:
        return 0

    pod_dir = REPO_ROOT / "podcasts" / args.date
    pod_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nDownloading {len(todo)} published episode(s)...")
    for tag in todo:
        topic = tag.split(marker, 1)[1]
        dest = pod_dir / f"{topic}.mp3"
        if dest.exists():
            continue
        r = subprocess.run(
            ["gh", "release", "download", tag, "--repo", repo,
             "--pattern", "*.mp3", "--dir", str(pod_dir), "--clobber"],
            capture_output=True, text=True, timeout=600,
        )
        if r.returncode != 0:
            print(f"  ✗ {topic}: {r.stderr.strip()[:160]}")
            continue
        # The asset is named after the topic already; rename only if it isn't.
        got = sorted(pod_dir.glob("*.mp3"))
        if not dest.exists() and got:
            got[-1].rename(dest)
        print(f"  ↓ {topic}: {dest.stat().st_size / 1048576:.1f} MB")

    print("\nJudging...")
    subprocess.run(
        [sys.executable, "-u", str(SCRIPTS_DIR / "qc_review.py"),
         "--date", args.date],
        env=env, check=False, timeout=5400,
    )

    verdicts = _existing_verdicts(args.date)
    if not verdicts:
        print("The judge produced no verdicts — nothing to act on."); return 1

    held = []
    for tag in todo:
        topic = tag.split(marker, 1)[1]
        v = verdicts.get(topic)
        if not v:
            print(f"  {topic}: still no verdict"); continue
        print(f"  {topic}: {v.get('accuracy')}/{v.get('coverage')}/"
              f"{v.get('fluency')} verdict={v.get('verdict')}")
        if not w._qc_should_hold(v):
            continue
        held.append(topic)
        if args.judge_only:
            print(f"    ⚠ would be HELD (left published: --judge-only)")
            continue
        r = subprocess.run(
            ["gh", "release", "edit", tag, "--repo", repo, "--draft"],
            capture_output=True, text=True, timeout=120,
        )
        print(f"    {'⏸️  pulled back to draft' if r.returncode == 0 else f'✗ could not unpublish: {r.stderr.strip()[:120]}'}")

    # Record durations and drop the local copies we just downloaded.
    for mp3 in sorted(pod_dir.glob("*.mp3")):
        w.release_local_audio(mp3.stem, str(mp3), args.date)
    try:
        pod_dir.rmdir()
    except OSError:
        pass

    if held and not args.judge_only:
        print(f"\n{len(held)} episode(s) pulled back; rebuilding feeds...")
        subprocess.run([sys.executable, "-u", str(SCRIPTS_DIR / "generate_rss.py")],
                       env=env, check=False, timeout=180)
        w.commit_and_push_feeds(f"feed: retroactive QC for {args.date}")
    print(f"\nDone: {len(todo)} judged, {len(held)} failed the gate"
          + (" (left published — --judge-only)" if args.judge_only else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
