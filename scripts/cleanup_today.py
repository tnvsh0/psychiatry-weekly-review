#!/usr/bin/env python3
"""
Cleanup helper — wipes today's run so the pipeline can be re-executed cleanly.

Use this when you want to re-run the weekly review with updated code on a
day the VM has already produced its automated run. Without cleanup,
`gh release create` would fail on the existing tags.

Removes (in order):
  1. Today's [PsychReview] notebooks on NotebookLM
  2. Today's `weekly-YYYY-MM-DD-*` GitHub Releases (and their tags)
  3. Today's `summaries/YYYY-MM-DD/` and `podcasts/YYYY-MM-DD/` directories

Run with `--dry-run` first to see what would be deleted.

Designed to run on the VM (where NotebookLM auth is valid). Run as the same
user that runs the weekly review (User), so `notebooklm` finds the auth file.

Usage:
    python scripts/cleanup_today.py --dry-run     # preview only
    python scripts/cleanup_today.py               # actually delete
    python scripts/cleanup_today.py --date 2026-05-17   # different date
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def _run(cmd: list[str], dry_run: bool, env: dict | None = None,
         capture: bool = True, timeout: int = 60):
    """Run a command (or just print it under --dry-run). Returns CompletedProcess."""
    print(f"  $ {' '.join(cmd)}")
    if dry_run:
        return None
    return subprocess.run(
        cmd, capture_output=capture, text=True, env=env, timeout=timeout,
    )


def cleanup_notebooks(date_str: str, dry_run: bool, env: dict) -> int:
    """Delete all [PsychReview] notebooks dated `date_str`. Returns count."""
    print(f"\n📓 Looking for [PsychReview] notebooks dated {date_str}...")
    try:
        result = subprocess.run(
            ["notebooklm", "list", "--json"],
            capture_output=True, text=True, env=env, timeout=60,
        )
    except Exception as e:
        print(f"  ERROR: could not list notebooks: {e}")
        return 0

    if result.returncode != 0:
        print(f"  ERROR: notebooklm list returned {result.returncode}")
        print(f"  stderr: {result.stderr[:300]}")
        return 0

    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        print(f"  ERROR: notebooklm list returned non-JSON output")
        return 0

    if isinstance(data, dict) and data.get("error"):
        print(f"  ERROR: {data.get('message', data)}")
        return 0

    notebooks = data.get("notebooks", []) if isinstance(data, dict) else []
    targets = [
        n for n in notebooks
        if n.get("title", "").startswith("[PsychReview]") and date_str in n.get("title", "")
    ]
    if not targets:
        print(f"  No [PsychReview] notebooks found for {date_str}.")
        return 0

    print(f"  Found {len(targets)} notebook(s) to delete:")
    for n in targets:
        print(f"    - {n.get('id','?')}  {n.get('title','?')}")

    if dry_run:
        return len(targets)

    deleted = 0
    for n in targets:
        nb_id = n.get("id")
        if not nb_id:
            continue
        try:
            r = subprocess.run(
                ["notebooklm", "delete", "-n", nb_id, "--yes"],
                capture_output=True, text=True, env=env, timeout=30,
            )
            if r.returncode == 0:
                deleted += 1
                print(f"    ✓ Deleted {nb_id}")
            else:
                print(f"    ✗ Failed {nb_id}: {r.stderr[:200]}")
        except Exception as e:
            print(f"    ✗ Error deleting {nb_id}: {e}")
    return deleted


def cleanup_releases(date_str: str, dry_run: bool, env: dict, repo: str) -> int:
    """Delete all weekly-{date_str}-* releases (and their tags). Returns count."""
    print(f"\n🏷️  Looking for GitHub releases tagged weekly-{date_str}-*...")
    try:
        r = subprocess.run(
            ["gh", "release", "list",
             "--repo", repo,
             "--limit", "100",
             "--json", "tagName"],
            capture_output=True, text=True, env=env, timeout=30,
        )
    except Exception as e:
        print(f"  ERROR: could not list releases: {e}")
        return 0

    if r.returncode != 0:
        print(f"  ERROR: gh release list returned {r.returncode}: {r.stderr[:200]}")
        return 0

    try:
        releases = json.loads(r.stdout or "[]")
    except json.JSONDecodeError:
        print(f"  ERROR: gh release list returned non-JSON output")
        return 0

    prefix = f"weekly-{date_str}-"
    tags = [rel.get("tagName") for rel in releases
            if rel.get("tagName", "").startswith(prefix)]
    if not tags:
        print(f"  No releases found with prefix {prefix}.")
        return 0

    print(f"  Found {len(tags)} release(s) to delete:")
    for tag in tags:
        print(f"    - {tag}")

    if dry_run:
        return len(tags)

    deleted = 0
    for tag in tags:
        # --cleanup-tag also deletes the underlying git tag
        try:
            r = subprocess.run(
                ["gh", "release", "delete", tag,
                 "--repo", repo,
                 "--cleanup-tag", "--yes"],
                capture_output=True, text=True, env=env, timeout=30,
            )
            if r.returncode == 0:
                deleted += 1
                print(f"    ✓ Deleted release + tag {tag}")
            else:
                print(f"    ✗ Failed {tag}: {r.stderr[:200]}")
        except Exception as e:
            print(f"    ✗ Error deleting {tag}: {e}")
    return deleted


def cleanup_local_dirs(date_str: str, dry_run: bool) -> int:
    """Remove local summaries/{date_str}/ and podcasts/{date_str}/ dirs."""
    print(f"\n📁 Looking for local dirs dated {date_str}...")
    removed = 0
    for base in ("summaries", "podcasts"):
        d = Path(base) / date_str
        if d.exists():
            print(f"  Will remove: {d}")
            if not dry_run:
                shutil.rmtree(d)
                removed += 1
                print(f"    ✓ Removed {d}")
        else:
            print(f"  Not present: {d}")
    return removed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    ap.add_argument("--date", default=datetime.utcnow().strftime("%Y-%m-%d"),
                    help="Date to clean (default: today UTC)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would be deleted, but don't delete")
    ap.add_argument("--skip-notebooks", action="store_true",
                    help="Skip NotebookLM cleanup (e.g. if running off-VM)")
    ap.add_argument("--skip-releases", action="store_true",
                    help="Skip GitHub Releases cleanup")
    ap.add_argument("--skip-local", action="store_true",
                    help="Skip local directory cleanup")
    args = ap.parse_args()

    # Validate date
    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        print(f"ERROR: --date must be YYYY-MM-DD, got: {args.date}")
        return 2

    env = os.environ.copy()
    repo = env.get("GH_REPO") or env.get("GITHUB_REPOSITORY") or "tnvsh0/psychiatry-weekly-review"

    print("=" * 70)
    print(f"Cleanup of today's run — {args.date}")
    print(f"  Repo: {repo}")
    print(f"  Mode: {'DRY RUN (no changes)' if args.dry_run else 'LIVE (will delete)'}")
    print("=" * 70)

    nb_count = 0
    rel_count = 0
    dir_count = 0

    if not args.skip_notebooks:
        nb_count = cleanup_notebooks(args.date, args.dry_run, env)
    else:
        print("\n📓 Skipping NotebookLM cleanup (--skip-notebooks).")

    if not args.skip_releases:
        rel_count = cleanup_releases(args.date, args.dry_run, env, repo)
    else:
        print("\n🏷️  Skipping GitHub Releases cleanup (--skip-releases).")

    if not args.skip_local:
        dir_count = cleanup_local_dirs(args.date, args.dry_run)
    else:
        print("\n📁 Skipping local-dir cleanup (--skip-local).")

    print("\n" + "=" * 70)
    print("Cleanup summary:")
    print(f"  Notebooks deleted: {nb_count}")
    print(f"  Releases deleted:  {rel_count}")
    print(f"  Local dirs cleared: {dir_count}")
    if args.dry_run:
        print("\n  (DRY RUN — re-run without --dry-run to actually delete.)")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
