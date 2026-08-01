#!/usr/bin/env python3
"""
Regenerate ONE episode (e.g. a QC-flagged one) and replace its audio.

NotebookLM is non-deterministic, so re-generating a bad episode usually yields a
different — often cleaner — take. This reuses the notebook + the exact prompt
saved in summaries/<date>/run-manifest.json (notebooks survive ~4 weeks).

    python scripts/regenerate_episode.py --date 2026-07-12 --topic neuroscience_part1
    python scripts/regenerate_episode.py --date 2026-07-12 --topic ... --publish

Steps: generate a fresh audio for the notebook → wait → download → replace the
release asset. By default the release keeps its current state (a held draft
stays a draft); pass --publish to also make it public + rebuild the feeds.
After regenerating it runs a quick single-episode QC and prints the new scores.

Must run where `notebooklm` is authenticated and `gh` is set up (the VM).
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


def _repo() -> str:
    repo = os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        print("ERROR: GH_REPO not set."); sys.exit(1)
    return repo


def _manifest_entry(date_str: str, topic_id: str) -> dict:
    mf = REPO_ROOT / "summaries" / date_str / "run-manifest.json"
    if not mf.exists():
        print(f"ERROR: no run-manifest.json for {date_str}."); sys.exit(1)
    data = json.loads(mf.read_text(encoding="utf-8"))
    if topic_id not in data:
        print(f"ERROR: {topic_id} not in manifest. Available: "
              f"{', '.join(data.keys())}"); sys.exit(1)
    return data[topic_id]


def _generate_and_download(nb_id: str, full_prompt: str, out_path: Path,
                           env: dict) -> bool:
    print("  Starting NotebookLM audio generation...")
    out = subprocess.run(
        ["notebooklm", "generate", "audio", full_prompt,
         "--format", "deep-dive", "--length", "long", "--language", "he",
         "-n", nb_id, "--json"],
        capture_output=True, text=True, env=env, timeout=120,
    )
    try:
        artifact_id = json.loads(out.stdout.strip()).get("task_id")
    except Exception:
        print(f"  ✗ generate failed: {out.stdout[:150]} {out.stderr[:150]}")
        return False
    if not artifact_id:
        print("  ✗ no artifact id returned."); return False
    print(f"  artifact {artifact_id}; waiting (up to 30 min)...")
    subprocess.run(
        ["notebooklm", "artifact", "wait", artifact_id, "-n", nb_id,
         "--timeout", "1800"],
        env=env, check=False, timeout=1900,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    dl = subprocess.run(
        ["notebooklm", "download", "audio", str(out_path),
         "-a", artifact_id, "-n", nb_id],
        capture_output=True, text=True, env=env, timeout=300,
    )
    if dl.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
        mb = out_path.stat().st_size / (1024 * 1024)
        print(f"  ✓ downloaded {out_path.name} ({mb:.1f} MB)")
        return True
    print(f"  ✗ download failed: {dl.stderr[:150]}")
    return False


def _current_prompt(date_str: str, topic_id: str) -> str | None:
    """Rebuild this episode's full prompt from the CURRENT topic definitions."""
    try:
        import weekly_review as w
    except Exception:
        return None
    base_id = topic_id.split("_part")[0]
    topic = next((t for t in w.TOPICS if t["id"] == base_id), None)
    if topic is None:
        return None
    prompt = topic["podcast_prompt"]
    if "_part" in topic_id:
        arts_p = REPO_ROOT / "summaries" / date_str / "articles.json"
        n_parts = 2
        if arts_p.exists():
            try:
                arts = json.loads(arts_p.read_text(encoding="utf-8"))
                n_parts = len({a["topic_id"] for a in arts
                               if a.get("topic_id", "").startswith(base_id + "_part")}) or 2
            except Exception:
                pass
        idx = topic_id.rsplit("_part", 1)[1]
        prompt += (
            f"\n\n[NOTE: This is part {idx} of {n_parts} for this topic. The "
            f"source material contains only the papers assigned to this part. "
            f"Cover them as a coherent stand-alone episode without referring to "
            f"'part 1' or 'part 2' explicitly.]"
        )
    return prompt + w._intro_directive_for(topic_id) + w.TONE_GUIDANCE


def _quick_qc(date_str: str, topic_id: str, mp3: Path) -> dict | None:
    """Best-effort single-episode QC — prints the new scores and returns the
    verdict so the caller can decide whether it is safe to publish."""
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
    print("  Re-running QC on the regenerated episode...")
    v = qc_review.judge_episode(client, types, mp3,
                                src.read_text(encoding="utf-8"),
                                os.environ.get("QC_MODEL", "gemini-2.5-flash"))
    if v:
        print(f"  → NEW scores: verdict={v.get('verdict')} "
              f"accuracy={v.get('accuracy')} coverage={v.get('coverage')} "
              f"fluency={v.get('fluency')}")
    return v


def main() -> int:
    ap = argparse.ArgumentParser(description="Regenerate one episode's audio.")
    ap.add_argument("--date", required=True)
    ap.add_argument("--topic", required=True, help="topic_id (e.g. neuroscience_part1)")
    ap.add_argument("--publish", action="store_true",
                    help="also make the release public + rebuild feeds")
    args = ap.parse_args()

    repo = _repo()
    env = os.environ.copy()
    entry = _manifest_entry(args.date, args.topic)
    nb_id = entry.get("nb_id")
    tag = entry.get("release_tag") or f"weekly-{args.date}-{args.topic}"
    if not nb_id:
        print("ERROR: manifest entry missing nb_id."); return 1

    # Prefer a prompt rebuilt from the CURRENT topic definitions, so a
    # regenerated episode benefits from every prompt fix made since the original
    # run. Fall back to the prompt recorded in the manifest.
    full_prompt = _current_prompt(args.date, args.topic) or entry.get("full_prompt", "")
    if not full_prompt:
        print("ERROR: could not build a prompt for this episode."); return 1

    mp3 = REPO_ROOT / "podcasts" / args.date / f"{args.topic}.mp3"
    print(f"Regenerating {args.topic} ({args.date}) — notebook {nb_id}")
    if not _generate_and_download(nb_id, full_prompt, mp3, env):
        return 1

    # Replace the release asset (keeps the release's draft/public state as-is
    # unless --publish is given).
    print(f"  Replacing release asset on {tag}...")
    subprocess.run(["gh", "release", "upload", tag, str(mp3), "--clobber",
                    "--repo", repo], capture_output=True, text=True, timeout=300)

    verdict = _quick_qc(args.date, args.topic, mp3)

    if args.publish:
        # Publish only if the FRESH take actually passes the same gate — pushing
        # a still-broken episode live would defeat the whole point of holding it.
        import weekly_review as w
        if verdict and w._qc_should_hold(verdict):
            print("\n⏸️  The regenerated take still fails QC "
                  f"(verdict={verdict.get('verdict')}, "
                  f"accuracy={verdict.get('accuracy')}) — leaving it held. "
                  "Run again, or publish manually with publish_episode.py.")
            return 0
        print("  QC clean — publishing + rebuilding feeds...")
        subprocess.run([sys.executable, str(SCRIPTS_DIR / "publish_episode.py"),
                        "--date", args.date, "--topic", args.topic],
                       env=env, check=False, timeout=300)
    else:
        print("\n✅ Regenerated. The release keeps its current state "
              "(a held draft stays held). Add --publish, or run "
              "publish_episode.py, when you're happy with it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
