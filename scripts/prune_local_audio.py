#!/usr/bin/env python3
"""
Reclaim the disk the pipeline used to leak: delete local episode MP3s that are
already published as GitHub Release assets.

Episodes were downloaded to podcasts/<date>/ and never cleaned up, so the shared
VM accumulated several GB of audio whose durable copy already lives in the
release (and in the Drive backup). Only the run in flight needs local audio.

Before deleting, each episode's DURATION is recorded into
summaries/<date>/durations.json, because generate_rss reads it from the local
file to emit <itunes:duration>. Without this step every past episode would
quietly lose its duration in the feed.

    python scripts/prune_local_audio.py --dry-run       # show what would go
    python scripts/prune_local_audio.py                 # prune everything old
    python scripts/prune_local_audio.py --keep-days 3   # leave recent runs alone

Safe to re-run; it only ever removes files it has just recorded a duration for.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _duration(mp3: Path) -> int | None:
    """These files are fragmented MPEG-4, not MP3, whatever the extension says,
    so mutagen.mp3 fails on every one of them -- this tool reported "no readable
    duration" for all 8 files on 2026-08-24 and would have deleted them without
    recording anything. audio_duration reads the DASH sidx box, which is what
    the pipeline itself uses."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from audio_duration import duration_seconds
        return duration_seconds(str(mp3)) or None
    except Exception:
        return None


def _load(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser(description="Prune already-published local MP3s.")
    ap.add_argument("--keep-days", type=int, default=0,
                    help="keep runs newer than this many days (default: 0)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    pod_root = REPO_ROOT / "podcasts"
    if not pod_root.exists():
        print("No podcasts/ directory — nothing to prune.")
        return 0

    cutoff = None
    if args.keep_days > 0:
        cutoff = (datetime.utcnow() - timedelta(days=args.keep_days)).strftime("%Y-%m-%d")

    total_files = total_bytes = 0
    no_duration = 0
    for date_dir in sorted(pod_root.iterdir()):
        if not date_dir.is_dir():
            continue
        try:
            datetime.strptime(date_dir.name, "%Y-%m-%d")
        except ValueError:
            continue
        if cutoff and date_dir.name >= cutoff:
            print(f"  {date_dir.name}: kept (within --keep-days)")
            continue

        mp3s = sorted(date_dir.glob("*.mp3"))
        if not mp3s:
            continue

        dur_path = REPO_ROOT / "summaries" / date_dir.name / "durations.json"
        durations = _load(dur_path)
        freed = 0
        for mp3 in mp3s:
            topic_id = mp3.stem
            if topic_id not in durations:
                d = _duration(mp3)
                if d is None:
                    no_duration += 1
                else:
                    durations[topic_id] = d
            freed += mp3.stat().st_size
            if not args.dry_run:
                mp3.unlink()
        if durations and not args.dry_run:
            dur_path.parent.mkdir(parents=True, exist_ok=True)
            dur_path.write_text(json.dumps(durations, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        if not args.dry_run:
            try:
                date_dir.rmdir()
            except OSError:
                pass
        total_files += len(mp3s)
        total_bytes += freed
        print(f"  {date_dir.name}: {len(mp3s)} file(s), {freed/1048576:.0f} MB"
              f"{' (dry run)' if args.dry_run else ' freed'}"
              f"  durations recorded: {len(durations)}")

    verb = "would free" if args.dry_run else "freed"
    print(f"\n{verb} {total_bytes/1073741824:.2f} GB across {total_files} file(s).")
    if no_duration:
        print(f"note: {no_duration} file(s) had no readable duration "
              f"(unreadable or corrupt) — their feed entries omit it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
