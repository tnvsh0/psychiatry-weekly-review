#!/usr/bin/env python3
"""
One-shot retitle for existing GitHub Releases.

Background: older releases were titled with the dry cluster label
("ליבה — פסיכיאטריית ילד ומתבגר", "ילדים ומתבגרים — מגוון", ...) which is
opaque to anyone who didn't build the system. NotebookLM auto-generates a
much more engaging Hebrew title per audio artifact (e.g. "מדידת הנפש מהיער
ועד לגלי המוח"). This script walks through the releases of a given week,
finds the matching notebook, pulls the NotebookLM artifact title, and
updates the release title via `gh release edit`.

Only works for notebooks that still exist on NotebookLM — older than 4
weeks they may have been auto-cleaned by weekly_review.py's cleanup step.

Must run on the VM (where the NotebookLM session is valid).

Usage:
    python scripts/update_release_titles.py --date 2026-05-25
    python scripts/update_release_titles.py --date 2026-05-25 --dry-run
    python scripts/update_release_titles.py --weeks 2026-05-17,2026-05-25

Required environment:
    GH_TOKEN  — GitHub token for repository write access
    GH_REPO   — owner/repo (defaults to tnvsh0/psychiatry-weekly-review)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def _run_json(cmd: list[str], env: dict, timeout: int = 60) -> dict | list:
    """Run a command, parse stdout as JSON, return the parsed value.
    Returns {} on any failure (intentionally permissive — caller handles)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                env=env, timeout=timeout)
    except Exception as e:
        print(f"  ERROR running {cmd[0]} {cmd[1] if len(cmd) > 1 else ''}: {e}")
        return {}
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[:300]}")
        return {}
    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return {}


def list_psychreview_notebooks(env: dict) -> list[dict]:
    """Return all [PsychReview] notebooks currently on NotebookLM."""
    data = _run_json(["notebooklm", "list", "--json"], env)
    notebooks = data.get("notebooks", []) if isinstance(data, dict) else []
    return [n for n in notebooks if n.get("title", "").startswith("[PsychReview]")]


def artifact_title_for_notebook(nb_id: str, env: dict) -> str | None:
    """Return the title of the first completed Audio artifact in this notebook."""
    # Need to "use" the notebook first — notebooklm CLI is stateful.
    subprocess.run(["notebooklm", "use", nb_id],
                   capture_output=True, env=env, timeout=30)
    data = _run_json(["notebooklm", "artifact", "list", "--json"], env)
    artifacts = data.get("artifacts", []) if isinstance(data, dict) else []
    for a in artifacts:
        if a.get("type_id") == "audio" and a.get("status_id") == 3:  # 3 = completed
            title = (a.get("title") or "").strip()
            if title:
                return title
    return None


def list_releases(date_str: str, repo: str, env: dict) -> list[dict]:
    """Return all releases tagged weekly-{date_str}-*."""
    data = _run_json([
        "gh", "release", "list",
        "--repo", repo,
        "--limit", "100",
        "--json", "tagName,name",
    ], env)
    if not isinstance(data, list):
        return []
    prefix = f"weekly-{date_str}-"
    return [r for r in data if r.get("tagName", "").startswith(prefix)]


def _find_notebook_for_topic(notebooks: list[dict], date_str: str,
                              topic_id: str) -> dict | None:
    """Find the [PsychReview] notebook matching a (date, topic_id) release.

    The notebook title looks like one of:
        [PsychReview] (3/12) ליבה — פסיכיאטריית ילד ומתבגר — 2026-05-25
        [PsychReview] (11/12) מאמר סקירה: Stahl ... — 2026-05-25
    The release tag's topic_id is either a cluster id (e.g. 'psychotherapy')
    or 'spotlight_{pmid}'. We match by date + a unique part of the cluster
    label, OR by the pmid for spotlights."""
    candidates = [n for n in notebooks if date_str in n.get("title", "")]
    if not candidates:
        return None

    # Mapping from cluster topic_id → a substring guaranteed to appear in the
    # notebook's Hebrew label_he but NOT in any other cluster's label.
    cluster_signatures = {
        "child_adolescent_core":          "ליבה",
        "child_adolescent_highimpact":    "השפעה גבוהה",
        "child_adolescent_misc":          "מגוון",
        "general_psychiatry_clinical":    "כללית — קלינית",
        "general_psychiatry_bio":         "ביולוגית",
        "child_development":              "התפתחות הילד",
        "neuroscience":                   "מדעי המוח",
        "psychotherapy":                  "פסיכותרפיה",
        "behavioral_sciences":            "מדעי ההתנהגות",
        "cognition":                      "קוגניציה",
    }

    if topic_id.startswith("spotlight_"):
        pmid = topic_id.replace("spotlight_", "")
        # The notebook title for a spotlight contains the author name + a slice
        # of the article title — we can't easily reconstruct the pmid. Fall
        # back to matching by the article-title substring stored in the
        # release name (caller handles this).
        return None

    base = topic_id.split("_part")[0]
    signature = cluster_signatures.get(base)
    if not signature:
        return None
    part_match = re.search(r"_part(\d+)$", topic_id)
    part_num = int(part_match.group(1)) if part_match else None

    for nb in candidates:
        title = nb["title"]
        if signature not in title:
            continue
        if part_num is None:
            # Non-split topic — make sure the notebook itself isn't a "part"
            if "חלק" in title or "Part" in title:
                continue
            return nb
        # Split topic — match the part number
        if f"חלק {part_num}" in title or f"Part {part_num}" in title:
            return nb
    return None


def _find_notebook_for_spotlight(notebooks: list[dict], date_str: str,
                                  rel_name: str) -> dict | None:
    """For spotlight releases, match by article title fragment."""
    candidates = [n for n in notebooks if date_str in n.get("title", "")]
    # Pull the spotlight's article-title fragment from the release name.
    # Release name format: "📚 (N/M) מאמר סקירה: Author — Title... — DATE"
    cleaned = rel_name.replace("📚 ", "").strip()
    cleaned = re.sub(r"\(\d+/\d+\)\s*", "", cleaned).strip()
    parts = cleaned.split(" — ")
    if len(parts) < 3:
        return None
    # parts[0] = "מאמר סקירה: Author"  → use just "מאמר סקירה"
    # parts[1] = the article title slice  → use as the unique marker
    title_slice = parts[1].strip()
    if not title_slice:
        return None
    for nb in candidates:
        if title_slice in nb["title"]:
            return nb
    return None


def update_release_title(tag: str, new_title: str, repo: str, env: dict,
                          dry_run: bool) -> bool:
    print(f"    new: {new_title}")
    if dry_run:
        return True
    r = subprocess.run([
        "gh", "release", "edit", tag,
        "--title", new_title,
        "--repo", repo,
    ], capture_output=True, text=True, env=env, timeout=30)
    if r.returncode != 0:
        print(f"    FAILED: {r.stderr[:300]}")
        return False
    return True


def process_week(date_str: str, notebooks: list[dict], repo: str,
                  env: dict, dry_run: bool) -> tuple[int, int, int]:
    """Process all releases for one week. Returns (updated, skipped, failed)."""
    print(f"\n=== Week {date_str} ===")
    releases = list_releases(date_str, repo, env)
    print(f"  Found {len(releases)} release(s) tagged weekly-{date_str}-*")

    updated = skipped = failed = 0
    for rel in releases:
        tag      = rel["tagName"]
        topic_id = tag[len(f"weekly-{date_str}-"):]
        rel_name = rel.get("name", "")
        old_title = rel_name

        print(f"\n  {tag}")
        print(f"    old: {old_title}")

        # Find the matching notebook
        if topic_id.startswith("spotlight_"):
            nb = _find_notebook_for_spotlight(notebooks, date_str, rel_name)
        else:
            nb = _find_notebook_for_topic(notebooks, date_str, topic_id)

        if not nb:
            print(f"    SKIP: no matching notebook found (deleted? > 4 weeks old?)")
            skipped += 1
            continue

        # Get the artifact title
        artifact_title = artifact_title_for_notebook(nb["id"], env)
        if not artifact_title:
            print(f"    SKIP: no completed audio artifact title in notebook {nb['id']}")
            skipped += 1
            continue

        new_title = f"\U0001f4da {artifact_title} — {date_str}"
        if new_title == old_title:
            print(f"    SKIP: already correct")
            skipped += 1
            continue

        if update_release_title(tag, new_title, repo, env, dry_run):
            updated += 1
        else:
            failed += 1

    return updated, skipped, failed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    ap.add_argument("--date", action="append", default=[],
                    help="One date to process (YYYY-MM-DD). Repeatable.")
    ap.add_argument("--weeks", default="",
                    help="Comma-separated list of dates (alternative to --date)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would change, don't actually edit")
    args = ap.parse_args()

    dates: list[str] = list(args.date)
    if args.weeks:
        dates.extend(s.strip() for s in args.weeks.split(",") if s.strip())
    if not dates:
        print("ERROR: pass at least one --date YYYY-MM-DD or --weeks d1,d2")
        return 2

    # Validate dates
    for d in dates:
        try:
            datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            print(f"ERROR: bad date {d!r} — expected YYYY-MM-DD")
            return 2

    env  = os.environ.copy()
    repo = env.get("GH_REPO") or env.get("GITHUB_REPOSITORY") or "tnvsh0/psychiatry-weekly-review"
    if not env.get("GH_TOKEN") and not env.get("GITHUB_TOKEN"):
        print("WARNING: GH_TOKEN not set — gh release edit will likely fail")

    print("=" * 70)
    print("Retitle existing releases using NotebookLM artifact titles")
    print(f"  Repo: {repo}")
    print(f"  Dates: {', '.join(dates)}")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("=" * 70)

    print("\nFetching NotebookLM notebooks...")
    notebooks = list_psychreview_notebooks(env)
    print(f"  Found {len(notebooks)} [PsychReview] notebook(s)")

    totals = {"updated": 0, "skipped": 0, "failed": 0}
    for date_str in dates:
        u, s, f = process_week(date_str, notebooks, repo, env, args.dry_run)
        totals["updated"] += u
        totals["skipped"] += s
        totals["failed"]  += f

    print("\n" + "=" * 70)
    print(f"Summary: {totals['updated']} updated, "
          f"{totals['skipped']} skipped, {totals['failed']} failed")
    if args.dry_run:
        print("(DRY RUN — re-run without --dry-run to apply.)")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
