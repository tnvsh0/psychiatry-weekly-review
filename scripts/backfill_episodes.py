#!/usr/bin/env python3
"""
Backfill episodes that were NEVER produced — their articles got a summary but
the podcast generation failed (historically: a rate-limited start returned None
and the episode was silently dropped).

Different from regenerate_episode.py: that one REPLACES the audio of an existing
release; this one CREATES the missing release from scratch.

    # see what's missing, change nothing:
    python scripts/backfill_episodes.py --date 2026-07-19 --dry-run
    # produce every missing episode of that date:
    python scripts/backfill_episodes.py --date 2026-07-19
    # just one:
    python scripts/backfill_episodes.py --date 2026-07-19 --topic neuroscience_part2

"Missing" = a topic_id present in summaries/<date>/articles.json that has no
GitHub release tagged weekly-<date>-<topic_id>.

The notebook is reused (they live ~4 weeks) — from summaries/<date>/
run-manifest.json when present, otherwise located by its NotebookLM title.
The PROMPT is rebuilt from the CURRENT TOPICS/TONE_GUIDANCE, so a backfilled
episode benefits from every prompt fix made since the original run.

Run on the VM (needs `notebooklm` + `gh` authenticated).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
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


def _articles(date_str: str) -> list[dict]:
    p = REPO_ROOT / "summaries" / date_str / "articles.json"
    if not p.exists():
        print(f"ERROR: no summaries/{date_str}/articles.json"); sys.exit(1)
    return json.loads(p.read_text(encoding="utf-8"))


def _existing_release_topics(repo: str, date_str: str) -> set[str]:
    out = subprocess.run(
        ["gh", "release", "list", "--repo", repo, "--limit", "300"],
        capture_output=True, timeout=120,
    )
    txt = out.stdout.decode("utf-8", errors="replace")
    marker = f"weekly-{date_str}-"
    return {ln.split(marker)[1].split()[0] for ln in txt.splitlines() if marker in ln}


def _manifest(date_str: str) -> dict:
    p = REPO_ROOT / "summaries" / date_str / "run-manifest.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _label_he(topic_id: str, arts: list[dict]) -> str:
    """Hebrew label as it appears in the notebook title, from articles.json."""
    for a in arts:
        if a.get("topic_id") == topic_id:
            return a.get("topic_he", topic_id)
    return topic_id


def _find_notebook(label_he: str, date_str: str, env: dict) -> str | None:
    """Locate the notebook by its '[PsychReview] (N/M) <label> — <date>' title."""
    try:
        out = subprocess.run(["notebooklm", "list", "--json"],
                             capture_output=True, text=True, env=env, timeout=90)
        nbs = json.loads(out.stdout.strip() or "{}").get("notebooks", [])
    except Exception as e:
        print(f"    could not list notebooks: {e}")
        return None
    for nb in nbs:
        t = nb.get("title", "")
        if t.startswith("[PsychReview]") and date_str in t and label_he in t:
            return nb.get("id")
    return None


def _base_prompt(topic_id: str, arts: list[dict]) -> str | None:
    """Rebuild the episode's base prompt from the CURRENT topic definitions, so
    backfilled episodes get all prompt improvements made since the failed run."""
    base_id = topic_id.split("_part")[0]
    topic = next((t for t in w.TOPICS if t["id"] == base_id), None)
    if topic is None:
        return None
    prompt = topic["podcast_prompt"]
    if "_part" in topic_id:
        n_parts = len({a["topic_id"] for a in arts
                       if a.get("topic_id", "").startswith(base_id + "_part")})
        idx = topic_id.rsplit("_part", 1)[1]
        prompt += (
            f"\n\n[NOTE: This is part {idx} of {n_parts} for this topic. The "
            f"source material contains only the papers assigned to this part. "
            f"Cover them as a coherent stand-alone episode without referring to "
            f"'part 1' or 'part 2' explicitly.]"
        )
    return prompt


def backfill_batch(topic_ids: list[str], date_str: str, arts: list[dict],
                   manifest: dict, repo: str, env: dict) -> int:
    """Produce several missing episodes. Generations are STARTED for all of them
    first and then awaited together — NotebookLM renders in parallel on Google's
    side, so a batch costs about as much wall-clock as the slowest single
    episode (waiting one-by-one would blow past the VM's run window)."""
    # weekly_review's download/upload helpers key off its module-level DATE_STR.
    w.DATE_STR = date_str
    jobs: list[dict] = []

    # Phase 1 — start every generation.
    for i, topic_id in enumerate(topic_ids):
        label_he = _label_he(topic_id, arts)
        print(f"\n▶ {topic_id}  ({label_he})")
        nb_id = (manifest.get(topic_id) or {}).get("nb_id") or _find_notebook(
            label_he, date_str, env)
        if not nb_id:
            print("  ✗ notebook not found (deleted after 4 weeks?) — skipping.")
            continue
        prompt = _base_prompt(topic_id, arts)
        if not prompt:
            print("  ✗ could not rebuild the prompt — skipping.")
            continue
        artifact_id = w.start_podcast(nb_id, prompt, env, topic_id=topic_id)
        if not artifact_id:
            print("  ✗ generation failed to start.")
            continue
        print(f"  started (notebook {nb_id}, artifact {artifact_id})")
        jobs.append({
            "nb_id": nb_id, "artifact_id": artifact_id, "podcast_ready": False,
            "topic": {"id": topic_id, "label_en": topic_id, "label_he": label_he},
        })
        if i < len(topic_ids) - 1:
            time.sleep(30)   # spacing so we don't trip the rate limit

    if not jobs:
        return 0

    # Phase 2 — wait for them all together.
    print(f"\nWaiting for {len(jobs)} generation(s)...")
    w.wait_for_all_podcasts(jobs, env, max_wait=5400)

    # Phase 3 — download, QC, then create the missing releases. Backfilled
    # episodes go through the SAME quality gate as normal ones: a failing
    # episode is published as a draft (excluded from the feed) for review
    # instead of going straight to Spotify unchecked.
    ok = 0
    verdicts: dict[str, dict] = {}
    for j in jobs:
        tid = j["topic"]["id"]
        if not j.get("podcast_ready"):
            print(f"  ✗ {tid}: did not finish in time.")
            continue
        path = w.download_podcast(j["nb_id"], j["artifact_id"], tid, env)
        if not path:
            print(f"  ✗ {tid}: download failed.")
            continue

        verdict = _qc_episode(Path(path), tid, date_str)
        hold = w._qc_should_hold(verdict)
        if verdict:
            verdicts[tid] = {k: verdict.get(k) for k in
                             ("verdict", "accuracy", "coverage", "fluency")}
            print(f"    QC: {verdict.get('verdict')} "
                  f"(acc {verdict.get('accuracy')}, cov {verdict.get('coverage')}, "
                  f"flu {verdict.get('fluency')})")
        url = w.upload_to_github_release(
            path, {"id": tid, "label_he": j["topic"]["label_he"],
                   "label_en": tid},
            env, artifact_title=j.get("artifact_title"), draft=hold,
        )
        print(f"  {'⏸️ held (draft)' if hold else '✓ published'} {tid}: {url}")
        ok += 1

    if verdicts:
        _merge_qc_results(date_str, verdicts)
    return ok


def _qc_episode(mp3: Path, topic_id: str, date_str: str) -> dict | None:
    """Run the normal Gemini QC judge on one backfilled episode."""
    src = REPO_ROOT / "summaries" / date_str / f"{topic_id}.md"
    if not src.exists():
        return None
    try:
        import qc_review
    except Exception:
        return None
    client, types = qc_review._gemini_client()
    if client is None:
        return None
    print(f"    QC: judging {topic_id}...")
    return qc_review.judge_episode(
        client, types, mp3, src.read_text(encoding="utf-8"),
        os.environ.get("QC_MODEL", "gemini-2.5-flash"),
    )


def _merge_qc_results(date_str: str, verdicts: dict) -> None:
    """Fold the backfilled episodes' verdicts into that date's qc-results.json
    so the record of the week is complete."""
    p = REPO_ROOT / "summaries" / date_str / "qc-results.json"
    data = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
    data.update(verdicts)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    subprocess.run(["git", "add", str(p)], check=False)
    print(f"    QC results merged into summaries/{date_str}/qc-results.json")


def _recent_dates(n: int) -> list[str]:
    """The N most recent summaries/<date> folders that have an articles.json,
    newest first. Bounded to ~4 weeks because notebooks are deleted after that
    and can no longer be regenerated."""
    from datetime import datetime, timedelta
    root = REPO_ROOT / "summaries"
    if not root.exists():
        return []
    cutoff = (datetime.utcnow() - timedelta(days=26)).strftime("%Y-%m-%d")
    dates = []
    for sub in root.iterdir():
        if not sub.is_dir() or not (sub / "articles.json").exists():
            continue
        try:
            datetime.strptime(sub.name, "%Y-%m-%d")
        except ValueError:
            continue
        if sub.name >= cutoff:
            dates.append(sub.name)
    return sorted(dates, reverse=True)[:n]


def _sweep(n: int, limit: int, dry_run: bool) -> int:
    """Self-heal pass: backfill anything missing across the recent runs.

    Safe to run every week — when nothing is missing it does nothing. Episodes
    whose notebook has aged out are reported and skipped, so a permanently
    unrecoverable episode can't cause an endless retry loop."""
    repo = _repo()
    env = os.environ.copy()
    dates = _recent_dates(n)
    print(f"🩹 Backfill sweep over {len(dates)} recent run(s): {', '.join(dates)}")
    budget = limit or 0
    total = 0
    for date_str in dates:
        arts = _articles(date_str)
        topics = sorted({a["topic_id"] for a in arts})
        present = _existing_release_topics(repo, date_str)
        missing = [t for t in topics if t not in present]
        if not missing:
            print(f"  {date_str}: complete.")
            continue
        print(f"  {date_str}: {len(missing)} missing -> {', '.join(missing)}")
        if dry_run:
            continue
        if budget:
            missing = missing[:budget]
        ok = backfill_batch(missing, date_str, arts, _manifest(date_str),
                            repo, env)
        total += ok
        if budget:
            budget -= ok
            if budget <= 0:
                print("  (episode budget for this sweep is used up)")
                break
    if total:
        print(f"\nBackfilled {total} episode(s); rebuilding feeds...")
        subprocess.run([sys.executable, str(SCRIPTS_DIR / "generate_rss.py")],
                       env=env, check=False, timeout=180)
        for feed in (REPO_ROOT / "docs").glob("feed*.xml"):
            subprocess.run(["git", "add", str(feed)], check=False)
        if subprocess.run(["git", "diff", "--cached", "--quiet"],
                          capture_output=True).returncode != 0:
            subprocess.run(["git", "commit", "-m",
                            "feed: backfill missing episodes"],
                           capture_output=True, check=False)
            subprocess.run(["git", "push", "origin", "main"],
                           capture_output=True, check=False)
            print("Feeds pushed.")
    elif not dry_run:
        print("Nothing to backfill.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill never-produced episodes.")
    ap.add_argument("--date", help="YYYY-MM-DD of the run")
    ap.add_argument("--recent", type=int, metavar="N",
                    help="sweep the N most recent run dates instead of --date "
                         "(used by the automatic Wednesday self-heal)")
    ap.add_argument("--topic", help="only this topic_id")
    ap.add_argument("--dry-run", action="store_true", help="list what's missing")
    ap.add_argument("--limit", type=int, default=0, help="cap episodes this run")
    args = ap.parse_args()

    if args.recent:
        return _sweep(args.recent, args.limit, args.dry_run)
    if not args.date:
        print("Give --date YYYY-MM-DD or --recent N."); return 2

    repo = _repo()
    env = os.environ.copy()
    arts = _articles(args.date)
    topics = sorted({a["topic_id"] for a in arts})
    present = _existing_release_topics(repo, args.date)
    missing = [t for t in topics if t not in present]
    if args.topic:
        missing = [t for t in missing if t == args.topic] or (
            [args.topic] if args.topic in topics else [])

    counts = {t: sum(1 for a in arts if a["topic_id"] == t) for t in topics}
    print(f"{args.date}: {len(topics)} topics, {len(present)} already published, "
          f"{len(missing)} missing")
    for t in missing:
        print(f"  - {t}  ({counts.get(t, '?')} articles)")
    if not missing:
        return 0
    if args.dry_run:
        print("\n(dry run — nothing generated)")
        return 0
    if args.limit:
        missing = missing[:args.limit]

    ok = backfill_batch(missing, args.date, arts, _manifest(args.date), repo, env)

    print(f"\n=== backfilled {ok}/{len(missing)} episode(s) for {args.date} ===")
    if ok:
        print("Rebuilding RSS feeds...")
        subprocess.run([sys.executable, str(SCRIPTS_DIR / "generate_rss.py")],
                       env=env, check=False, timeout=180)
        for feed in (REPO_ROOT / "docs").glob("feed*.xml"):
            subprocess.run(["git", "add", str(feed)], check=False)
        if subprocess.run(["git", "diff", "--cached", "--quiet"],
                          capture_output=True).returncode != 0:
            subprocess.run(["git", "commit", "-m",
                            f"feed: backfill missing episodes for {args.date}"],
                           capture_output=True, check=False)
            subprocess.run(["git", "push", "origin", "main"],
                           capture_output=True, check=False)
            print("Feeds pushed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
