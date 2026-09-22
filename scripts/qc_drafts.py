#!/usr/bin/env python3
"""
Judge episodes that were HELD as drafts, and publish the ones that pass.

The mirror image of qc_published.py. That one exists for episodes that went out
without a verdict; this one for episodes that never went out because no verdict
arrived in time.

That is not hypothetical. On 2026-09-20 the QC step was killed by a 50-minute
timeout after judging 11 of 13 episodes, Google's rate limiter pushed 7 more
generations to the next day, and 19 of 20 episodes spent the week as drafts —
most of them never judged at all. The gate did the right thing: an unjudged
episode is held. But nothing then went back to look at them.

This downloads the audio from the draft release (no regeneration — it is the
same audio a listener would have got), runs the ordinary judge, and publishes
the ones the ordinary gate would have published. Anything that fails stays a
draft, exactly where it is.

    python scripts/qc_drafts.py --date 2026-09-20 --dry-run
    python scripts/qc_drafts.py --date 2026-09-20
    python scripts/qc_drafts.py --date 2026-09-20 --judge-only   # score, publish nothing

Episodes that already carry a verdict are judged again only with --force; their
verdict already decided the matter.

Run on the VM (needs `gh` and agy).
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
from qc_published import _existing_verdicts, _repo  # noqa: E402

# A judge call through agy takes 3-5 minutes; allow for a retry each.
_PER_EPISODE_S = 8 * 60


def _draft_tags(repo: str, date_str: str) -> list[str]:
    """Draft releases for this date — the episodes the gate held back."""
    out = subprocess.run(
        ["gh", "api", f"repos/{repo}/releases?per_page=100", "--paginate",
         "--jq", ".[]|select(.draft)|.tag_name"],
        capture_output=True, text=True, timeout=120,
    )
    marker = f"weekly-{date_str}-"
    return sorted(ln.strip() for ln in out.stdout.splitlines() if marker in ln)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", required=True, help="YYYY-MM-DD run date")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="re-judge drafts that already carry a verdict")
    ap.add_argument("--judge-only", action="store_true",
                    help="write verdicts but publish nothing")
    args = ap.parse_args()

    repo = _repo()
    env = os.environ.copy()
    from agy_judge import agy_available
    if not (agy_available() or env.get("GEMINI_API_KEY")
            or env.get("GOOGLE_API_KEY")):
        print("ERROR: neither agy nor a Gemini key — the judge cannot run.")
        return 1

    tags = _draft_tags(repo, args.date)
    if not tags:
        print(f"No draft releases for {args.date}."); return 0

    marker = f"weekly-{args.date}-"
    have = _existing_verdicts(args.date)
    todo = [t for t in tags
            if args.force or not (have.get(t.split(marker, 1)[1]) or {}).get("accuracy")]

    print(f"{args.date}: {len(tags)} draft(s), {len(tags) - len(todo)} already "
          f"judged, {len(todo)} to judge")
    for t in todo:
        print(f"  - {t.split(marker, 1)[1]}")
    if args.dry_run:
        print("\n(dry run — nothing downloaded, judged or published)")
        return 0
    if not todo:
        print("Nothing to do: every draft already has a verdict "
              "(use --force to judge them again).")
        return 0

    pod_dir = REPO_ROOT / "podcasts" / args.date
    pod_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nDownloading {len(todo)} held episode(s)...")
    ready = []
    for tag in todo:
        topic = tag.split(marker, 1)[1]
        dest = pod_dir / f"{topic}.mp3"
        if not dest.exists():
            r = subprocess.run(
                ["gh", "release", "download", tag, "--repo", repo,
                 "--pattern", "*.mp3", "--dir", str(pod_dir), "--clobber"],
                capture_output=True, text=True, timeout=900,
            )
            if r.returncode != 0:
                print(f"  ✗ {topic}: {r.stderr.strip()[:160]}")
                continue
            got = sorted(pod_dir.glob("*.mp3"))
            if not dest.exists() and got:
                got[-1].rename(dest)
        if not dest.exists():
            print(f"  ✗ {topic}: no audio on the release")
            continue
        ready.append(tag)
        print(f"  ↓ {topic}: {dest.stat().st_size / 1048576:.1f} MB")

    if not ready:
        print("Nothing downloaded — stopping."); return 1

    # qc_review judges every MP3 in the folder, which is what we want: anything
    # already sitting there is an episode of this run too.
    n = len(list(pod_dir.glob("*.mp3")))
    print(f"\nJudging {n} episode(s) (up to {n * _PER_EPISODE_S // 60} min)...")
    subprocess.run(
        [sys.executable, "-u", str(SCRIPTS_DIR / "qc_review.py"),
         "--date", args.date],
        env=env, check=False, timeout=max(3600, n * _PER_EPISODE_S),
    )

    verdicts = _existing_verdicts(args.date)
    published, still_held, unjudged = [], [], []
    for tag in ready:
        topic = tag.split(marker, 1)[1]
        v = verdicts.get(topic)
        if not v or v.get("accuracy") is None:
            print(f"  {topic}: still no verdict — stays a draft")
            unjudged.append(topic)
            continue
        print(f"  {topic}: acc {v.get('accuracy')}, cov {v.get('coverage')}, "
              f"flu {v.get('fluency')}, verdict={v.get('verdict')}")
        if w._qc_should_hold(v):
            still_held.append(topic)
            print("    ⏸️  fails the gate — stays a draft")
            continue
        if args.judge_only:
            published.append(topic)
            print("    ✅ would be published (--judge-only)")
            continue
        r = subprocess.run(
            ["gh", "release", "edit", tag, "--repo", repo, "--draft=false"],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode == 0:
            published.append(topic)
            print("    ✅ published")
        else:
            still_held.append(topic)
            print(f"    ✗ could not publish: {r.stderr.strip()[:120]}")

    for mp3 in sorted(pod_dir.glob("*.mp3")):
        w.release_local_audio(mp3.stem, str(mp3), args.date)
    try:
        pod_dir.rmdir()
    except OSError:
        pass

    if published and not args.judge_only:
        print(f"\n{len(published)} episode(s) published; rebuilding feeds...")
        subprocess.run([sys.executable, "-u", str(SCRIPTS_DIR / "generate_rss.py")],
                       env=env, check=False, timeout=180)
        w.commit_and_push_feeds(f"feed: publish held episodes judged for {args.date}")

    print(f"\nDone: {len(published)} published, {len(still_held)} still held, "
          f"{len(unjudged)} without a verdict")
    return 0


if __name__ == "__main__":
    sys.exit(main())
