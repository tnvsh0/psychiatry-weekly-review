#!/usr/bin/env python3
"""
Re-fetch an episode's sources, swap them into its notebook, and regenerate it.

`regenerate_episode.py` re-rolls the dice with the same sources. That is the
right tool when the model simply had a bad take. It is the wrong tool when the
SOURCE was wrong — and for every run from 2026-09-06 to 2026-09-23 it was:
`efetch db=pmc rettype=full` returns JATS XML, the fetch stored it verbatim, and
one article in five reached NotebookLM as metadata boilerplate with the science
truncated away. Re-generating from that notebook reproduces the same hole.

So this rebuilds the chain from the top: re-fetch the article text with the
fixed parser, rewrite summaries/<date>/<topic>.md, replace the notebook's
sources, regenerate the audio (with the corrections the judge already wrote for
this episode), re-judge, and publish only what passes the ordinary gate.

    python scripts/refresh_sources_and_regenerate.py --date 2026-09-20 --held --dry-run
    python scripts/refresh_sources_and_regenerate.py --date 2026-09-20 --held --limit 5
    python scripts/refresh_sources_and_regenerate.py --date 2026-09-20 --topic cognition_part1

Episodes are done one at a time, and --limit keeps a batch small: Google rate-
limited seven generations in one morning on 2026-09-20, and a batch that trips
the limiter wastes the whole run. Run it again for the next batch.

Must run where `notebooklm` is authenticated and `gh` works (the VM).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import regenerate_episode as r  # noqa: E402
import weekly_review as w  # noqa: E402

# NotebookLM needs the new source indexed before it can speak about it. The
# weekly run waits 120s for markdown; a swap is the same shape of work.
INDEX_WAIT_S = 150


def _articles_for(date_str: str, topic_id: str) -> tuple[list[dict], list[dict]]:
    """(this episode's articles, the whole file) from summaries/<date>/articles.json."""
    p = REPO_ROOT / "summaries" / date_str / "articles.json"
    everything = json.loads(p.read_text(encoding="utf-8"))
    return [a for a in everything if a.get("topic_id") == topic_id], everything


def _save_articles(date_str: str, everything: list[dict]) -> None:
    p = REPO_ROOT / "summaries" / date_str / "articles.json"
    p.write_text(json.dumps(everything, ensure_ascii=False, indent=2),
                 encoding="utf-8")


def _topic_for(topic_id: str, label_he: str) -> dict | None:
    base = next((t for t in w.TOPICS if t["id"] == topic_id.split("_part")[0]), None)
    if base is None:
        return None
    return {**base, "id": topic_id, "label_he": label_he or base["label_he"]}


def _swap_sources(nb_id: str, md_path: str, env: dict) -> bool:
    """Delete every source in the notebook, then add the rebuilt markdown."""
    subprocess.run(["notebooklm", "use", nb_id], capture_output=True, env=env,
                   timeout=30)
    listed = subprocess.run(["notebooklm", "source", "list", "--json"],
                            capture_output=True, text=True, env=env, timeout=60)
    ids: list[str] = []
    try:
        data = json.loads(listed.stdout or "{}")
        rows = data if isinstance(data, list) else data.get("sources") or []
        ids = [s.get("id") for s in rows if isinstance(s, dict) and s.get("id")]
    except Exception:
        print("    ! could not read the notebook's source list")
    for sid in ids:
        subprocess.run(["notebooklm", "source", "delete", sid, "--yes"],
                       capture_output=True, env=env, timeout=60)
    print(f"    removed {len(ids)} old source(s)")
    added = subprocess.run(["notebooklm", "source", "add", md_path, "--json"],
                           capture_output=True, text=True, env=env, timeout=180)
    if added.returncode != 0:
        print(f"    ✗ could not add the new source: {added.stderr[:160]}")
        return False
    print(f"    added {Path(md_path).name}; waiting {INDEX_WAIT_S}s for indexing")
    time.sleep(INDEX_WAIT_S)
    return True


def _record_verdict(date_str: str, topic_id: str, verdict: dict) -> None:
    """Merge one verdict into summaries/<date>/qc-results.json."""
    try:
        import qc_review
        v = dict(verdict)
        v["topic_id"] = topic_id
        v.setdefault("title", topic_id)
        qc_review._write_results_json(date_str, [v])
    except Exception as e:
        print(f"    ! could not record the verdict: {e}")


def _held_topics(date_str: str) -> list[str]:
    """Topics whose release is still a draft, worst verdict first."""
    repo = r._repo()
    out = subprocess.run(
        ["gh", "api", f"repos/{repo}/releases?per_page=100", "--paginate",
         "--jq", ".[]|select(.draft)|.tag_name"],
        capture_output=True, text=True, timeout=120,
    )
    marker = f"weekly-{date_str}-"
    topics = sorted(ln.strip().split(marker, 1)[1]
                    for ln in out.stdout.splitlines() if marker in ln)
    try:
        q = json.loads((REPO_ROOT / "summaries" / date_str /
                        "qc-results.json").read_text(encoding="utf-8"))
    except Exception:
        q = {}
    return sorted(topics, key=lambda t: (q.get(t, {}).get("accuracy") or 5))


def _one(date_str: str, topic_id: str, env: dict, publish: bool) -> str:
    entry = r._manifest_entry(date_str, topic_id)
    nb_id, tag = entry.get("nb_id"), entry.get("release_tag") or f"weekly-{date_str}-{topic_id}"
    if not nb_id:
        return "no nb_id in the manifest"

    arts, everything = _articles_for(date_str, topic_id)
    if not arts:
        return "no articles recorded for this topic"
    topic = _topic_for(topic_id, entry.get("label_he", ""))
    if topic is None:
        return "topic id not in the current definitions"

    print(f"  re-fetching {len(arts)} article(s)...")
    before = sum(len(a.get("abstract") or "") for a in arts)
    was_xml = sum(1 for a in arts
                  if str(a.get("abstract") or "").lstrip().startswith("<?xml"))
    w.fetch_article_text(arts)
    after = sum(len(a.get("abstract") or "") for a in arts)
    print(f"    source text {before:,} -> {after:,} chars "
          f"({was_xml} article(s) had been raw XML)")
    _save_articles(date_str, everything)

    md = w.create_topic_summary(topic, arts)
    print(f"    rewrote {md}")

    if not _swap_sources(nb_id, md, env):
        return "could not replace the notebook's sources"

    prompt = r._current_prompt(date_str, topic_id) or entry.get("full_prompt", "")
    if not prompt:
        return "could not build a prompt"
    # Whatever the judge already found wrong with this episode goes to the next
    # take, the same way the books project carries corrections.
    try:
        q = json.loads((REPO_ROOT / "summaries" / date_str /
                        "qc-results.json").read_text(encoding="utf-8"))
        errors = w._gate_errors(q.get(topic_id))
    except Exception:
        errors = []
    if errors:
        print(f"    carrying {len(errors)} correction(s) from the last verdict")
        prompt += w._corrections_block(errors)

    mp3 = REPO_ROOT / "podcasts" / date_str / f"{topic_id}.mp3"
    if not r._generate_and_download(nb_id, prompt, mp3, env):
        return "generation or download failed"

    print(f"    replacing the release asset on {tag}")
    subprocess.run(["gh", "release", "upload", tag, str(mp3), "--clobber",
                    "--repo", r._repo()], capture_output=True, text=True,
                   timeout=600)

    verdict = r._quick_qc(date_str, topic_id, mp3)
    if not verdict:
        return "no verdict — stays held"
    _record_verdict(date_str, topic_id, verdict)
    if w._qc_should_hold(verdict):
        return (f"still fails the gate (acc {verdict.get('accuracy')}, "
                f"{sum(1 for d in verdict.get('discrepancies') or [] if d.get('severity') == 'high')} high) — stays held")
    if not publish:
        return f"PASSES (acc {verdict.get('accuracy')}) — not published (--no-publish)"
    subprocess.run([sys.executable, str(SCRIPTS_DIR / "publish_episode.py"),
                    "--date", date_str, "--topic", topic_id],
                   env=env, check=False, timeout=600)
    return f"PUBLISHED (acc {verdict.get('accuracy')})"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", required=True)
    ap.add_argument("--topic", action="append", default=[],
                    help="topic id; repeatable")
    ap.add_argument("--held", action="store_true",
                    help="every topic of this date whose release is a draft")
    ap.add_argument("--limit", type=int, default=5,
                    help="how many episodes this run (default 5)")
    ap.add_argument("--no-publish", action="store_true",
                    help="judge and leave the release as it is")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # weekly_review's writers are dated from module globals; point them at the
    # run being repaired so the rebuilt markdown lands in that run's folder.
    # Naive UTC, to match weekly_review's own TODAY = datetime.utcnow().
    day = datetime.strptime(args.date, "%Y-%m-%d")
    w.DATE_STR = args.date
    w.TODAY = day
    w.WEEK_START = day - timedelta(days=7)

    topics = list(dict.fromkeys(args.topic + (_held_topics(args.date) if args.held else [])))
    if not topics:
        print("Nothing to do: name --topic, or pass --held."); return 0
    print(f"{args.date}: {len(topics)} episode(s) to repair; "
          f"doing {min(args.limit, len(topics))} this run")
    for t in topics:
        print(f"  - {t}")
    if args.dry_run:
        print("\n(dry run — nothing fetched, swapped, generated or published)")
        return 0

    env = os.environ.copy()
    results: dict[str, str] = {}
    for topic_id in topics[:args.limit]:
        print(f"\n=== {topic_id} ===")
        try:
            results[topic_id] = _one(args.date, topic_id, env,
                                     publish=not args.no_publish)
        except Exception as e:
            results[topic_id] = f"ERROR: {e}"
        print(f"  → {results[topic_id]}")

    print("\n" + "=" * 64)
    for k, v in results.items():
        print(f"  {k:38s} {v}")
    left = topics[args.limit:]
    if left:
        print(f"\n{len(left)} episode(s) left for the next run: "
              f"{', '.join(left)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
