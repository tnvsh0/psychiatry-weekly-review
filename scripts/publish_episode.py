#!/usr/bin/env python3
"""
Publish an episode that the QC gate HELD as a draft (approve it → it goes live).

The weekly run uploads QC-flagged episodes as GitHub *draft* releases, which the
RSS feed excludes, so they never reach Spotify. After reviewing the QC report
(summaries/<date>/qc-report.md), run this to publish the ones you approve:

    python scripts/publish_episode.py --date 2026-07-12 --topic neuroscience_part1
    python scripts/publish_episode.py --date 2026-07-12 --all-held   # publish all held

It flips the release from draft → public, rebuilds every RSS feed, and commits +
pushes docs/feed*.xml so the episode appears on Spotify at the next poll.

Env: GH_REPO (owner/repo) and gh CLI authenticated (both already set on the VM).
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


def _repo() -> str:
    repo = os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        print("ERROR: GH_REPO not set."); sys.exit(1)
    return repo


def _held_topics(date_str: str) -> list[str]:
    """topic_ids the run marked as held, from run-manifest.json."""
    mf = REPO_ROOT / "summaries" / date_str / "run-manifest.json"
    if not mf.exists():
        return []
    try:
        data = json.loads(mf.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [tid for tid, m in data.items() if m.get("held")]


def _publish_release(repo: str, tag: str) -> bool:
    r = subprocess.run(
        ["gh", "release", "edit", tag, "--draft=false", "--repo", repo],
        capture_output=True, text=True, timeout=60,
    )
    if r.returncode == 0:
        print(f"  ✓ published release {tag}")
        return True
    print(f"  ✗ failed to publish {tag}: {r.stderr.strip()[:160]}")
    return False


def _rebuild_and_push_feeds(repo: str) -> None:
    env = os.environ.copy()
    env.setdefault("GH_REPO", repo)
    subprocess.run([sys.executable, str(SCRIPTS_DIR / "generate_rss.py")],
                   env=env, check=False, timeout=180)
    for feed in (REPO_ROOT / "docs").glob("feed*.xml"):
        subprocess.run(["git", "add", str(feed)], check=False)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"],
                            capture_output=True)
    if staged.returncode == 0:
        print("  No feed change to commit.")
        return
    subprocess.run(["git", "commit", "-m", "feed: publish approved episode(s)"],
                   capture_output=True, text=True, check=False)
    push = subprocess.run(["git", "push", "origin", "main"],
                          capture_output=True, text=True, check=False)
    print("  Feeds pushed." if push.returncode == 0
          else f"  WARNING: push failed: {push.stderr.strip()[:160]}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish a QC-held (draft) episode.")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD run date")
    ap.add_argument("--topic", help="topic_id to publish (e.g. neuroscience_part1)")
    ap.add_argument("--all-held", action="store_true",
                    help="publish every held episode of this date")
    args = ap.parse_args()

    repo = _repo()
    if args.all_held:
        topics = _held_topics(args.date)
        if not topics:
            print("No held episodes found for this date."); return 0
    elif args.topic:
        topics = [args.topic]
    else:
        print("Give --topic <id> or --all-held."); return 2

    print(f"Publishing {len(topics)} episode(s) for {args.date}...")
    published = 0
    for tid in topics:
        if _publish_release(repo, f"weekly-{args.date}-{tid}"):
            published += 1
    if published:
        print("\nRebuilding feeds...")
        _rebuild_and_push_feeds(repo)
        print(f"\n✅ Published {published} episode(s). They will appear on "
              f"Spotify at its next feed poll (usually within a few hours).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
