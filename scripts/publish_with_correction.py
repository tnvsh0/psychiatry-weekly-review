#!/usr/bin/env python3
"""
Publish a held episode with a spoken correction at its start.

An episode the gate holds is not always worth re-rendering. Often one number or
one reversed sentence is wrong and the other twenty minutes teach the papers
correctly — and holding it means nobody hears any of it. The general AI
disclaimer does not help there: it tells the listener to verify, not WHICH
sentence was wrong.

So: take what the judge already wrote, say it out loud at the top of the
episode, and publish.

    "לפני שמתחילים, תיקון לפרק הזה. נאמר בפרק ש... הנתון הנכון לפי המקור הוא...
     שאר הפרק לא השתנה."

The line the gate keeps: only findings the judge marked scope="detail" can be
corrected this way. A "core" finding means the episode's main message about a
paper is wrong, and a correction at the start cannot fix twenty minutes built on
it — that episode is regenerated, not annotated. More than MAX_CORRECTIONS
findings is also a regeneration: an episode that needs four corrections read out
before it starts is not an episode worth publishing.

    python scripts/publish_with_correction.py --date 2026-09-20 --topic behavioral_sciences
    python scripts/publish_with_correction.py --date 2026-09-20 --held --dry-run

Needs `gh`, and on the VM: ffmpeg, plus edge-tts or gTTS for the Hebrew voice.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import weekly_review as w  # noqa: E402
from qc_published import _existing_verdicts, _repo  # noqa: E402

# A deliberately different voice from the two hosts, so the correction is
# audibly an outside note and not part of the conversation.
EDGE_VOICE = os.environ.get("CORRECTION_VOICE", "he-IL-AvriNeural")
MAX_CORRECTIONS = 3


def _corrections_for(date_str: str, topic_id: str) -> tuple[list[dict], str]:
    """(correctable findings, reason to refuse) for one episode."""
    v = _existing_verdicts(date_str).get(topic_id) or {}
    if not v:
        return [], "no verdict on file"
    flagged = [d for d in (v.get("discrepancies") or [])
               if d.get("severity") == "high"]
    if not flagged:
        return [], "nothing high-severity — it should simply be published"
    core = [d for d in flagged if (d.get("scope") or "").lower() == "core"]
    if core:
        return [], (f"{len(core)} finding(s) marked core — the episode's own "
                    f"message is wrong, so it needs regenerating")
    unscored = [d for d in flagged if not d.get("scope")]
    if unscored:
        return [], (f"{len(unscored)} finding(s) have no scope — judged before "
                    f"the judge marked detail/core; re-judge it first")
    if len(flagged) > MAX_CORRECTIONS:
        return [], (f"{len(flagged)} findings, more than {MAX_CORRECTIONS} — "
                    f"too much to read out; regenerate instead")
    return flagged, ""


def correction_text(findings: list[dict]) -> str:
    """The Hebrew the voice reads. Short, plain, and specific."""
    parts = ["לפני שמתחילים, תיקון לפרק הזה."]
    if len(findings) > 1:
        parts.append(f"נמצאו {len(findings)} אי-דיוקים.")
    for d in findings:
        said = " ".join(str(d.get("said") or "").split())
        src = " ".join(str(d.get("source") or "").split())
        # The judge quotes the episode, often with a timestamp; keep it short
        # enough to stay a correction rather than a recap.
        if len(said) > 220:
            said = said[:220] + "..."
        if len(src) > 220:
            src = src[:220] + "..."
        parts.append(f"בפרק נאמר: {said}")
        if "לא מופיע במקור" in src:
            parts.append("הדבר אינו מופיע במקור, ואין להסתמך עליו.")
        else:
            parts.append(f"לפי המקור: {src}")
    parts.append("שאר הפרק לא השתנה.")
    return " ".join(parts)


def _tts(text: str, out: Path) -> bool:
    """Hebrew speech, without a paid API. edge-tts first, gTTS as the fallback."""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "edge_tts", "--voice", EDGE_VOICE,
             "--text", text, "--write-media", str(out)],
            capture_output=True, text=True, timeout=180,
        )
        if r.returncode == 0 and out.exists() and out.stat().st_size > 2000:
            return True
        print(f"  edge-tts failed ({r.stderr.strip()[:120]}) — trying gTTS")
    except Exception as e:
        print(f"  edge-tts unavailable ({e}) — trying gTTS")
    try:
        from gtts import gTTS
        gTTS(text=text, lang="iw").save(str(out))
        return out.exists() and out.stat().st_size > 2000
    except Exception as e:
        print(f"  gTTS failed too: {e}")
        return False


def _prepend(correction: Path, episode: Path, out: Path) -> bool:
    """Glue the correction in front of the episode.

    NotebookLM hands back a fragmented MP4/DASH container despite the .mp3
    name, so both inputs are decoded and re-encoded rather than stream-copied.
    """
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", str(correction), "-i", str(episode),
         "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[out]",
         "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "128k", str(out)],
        capture_output=True, text=True, timeout=3600,
    )
    if r.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        print(f"  ffmpeg failed: {r.stderr.strip()[-300:]}")
        return False
    return True


def _episode_audio(date_str: str, topic_id: str, tag: str, repo: str,
                   work: Path) -> Path | None:
    """The audio as published: local copy if present, else off the release."""
    local = REPO_ROOT / "podcasts" / date_str / f"{topic_id}.mp3"
    if local.exists() and local.stat().st_size > 0:
        return local
    r = subprocess.run(
        ["gh", "release", "download", tag, "--repo", repo,
         "--pattern", "*.mp3", "--dir", str(work), "--clobber"],
        capture_output=True, text=True, timeout=900,
    )
    if r.returncode != 0:
        print(f"  could not download the release asset: {r.stderr.strip()[:160]}")
        return None
    got = sorted(work.glob("*.mp3"))
    return got[-1] if got else None


def _one(date_str: str, topic_id: str, env: dict, dry_run: bool) -> str:
    findings, refusal = _corrections_for(date_str, topic_id)
    if refusal:
        return f"skipped — {refusal}"
    text = correction_text(findings)
    print(f"  correction ({len(findings)} finding(s)):\n    {text}")
    if dry_run:
        return "dry run — nothing built or published"

    repo = _repo()
    tag = f"weekly-{date_str}-{topic_id}"
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        episode = _episode_audio(date_str, topic_id, tag, repo, work)
        if episode is None:
            return "no audio to work with"
        spoken = work / "correction.mp3"
        if not _tts(text, spoken):
            return "no Hebrew voice available (install edge-tts or gTTS)"
        merged = work / f"{topic_id}.mp3"
        if not _prepend(spoken, episode, merged):
            return "could not prepend the correction"
        size_mb = merged.stat().st_size / 1048576
        print(f"  built {size_mb:.1f} MB with the correction in front")

        up = subprocess.run(
            ["gh", "release", "upload", tag, str(merged), "--clobber",
             "--repo", repo],
            capture_output=True, text=True, timeout=900,
        )
        if up.returncode != 0:
            return f"upload failed: {up.stderr.strip()[:160]}"
        # Keep the corrected copy where the rest of the pipeline expects it, so
        # the duration recorded in the feed is the corrected episode's.
        local = REPO_ROOT / "podcasts" / date_str / f"{topic_id}.mp3"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(merged.read_bytes())

    subprocess.run([sys.executable, str(SCRIPTS_DIR / "publish_episode.py"),
                    "--date", date_str, "--topic", topic_id],
                   env=env, check=False, timeout=600)
    _record(date_str, topic_id, text)
    return f"PUBLISHED with {len(findings)} spoken correction(s)"


def _record(date_str: str, topic_id: str, text: str) -> None:
    """Write what was corrected next to the verdicts, so the episode's history
    says why its audio differs from what NotebookLM produced."""
    p = REPO_ROOT / "summaries" / date_str / "corrections.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data[topic_id] = {"text": text, "added": w.DATE_STR}
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", required=True)
    ap.add_argument("--topic", action="append", default=[])
    ap.add_argument("--held", action="store_true",
                    help="every draft of this date that qualifies")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the correction each episode would get")
    args = ap.parse_args()

    topics = list(args.topic)
    if args.held:
        repo = _repo()
        out = subprocess.run(
            ["gh", "api", f"repos/{repo}/releases?per_page=100", "--paginate",
             "--jq", ".[]|select(.draft)|.tag_name"],
            capture_output=True, text=True, timeout=120,
        )
        marker = f"weekly-{args.date}-"
        topics += [ln.strip().split(marker, 1)[1]
                   for ln in out.stdout.splitlines() if marker in ln]
    topics = list(dict.fromkeys(topics))
    if not topics:
        print("Nothing to do: name --topic, or pass --held."); return 0

    env = os.environ.copy()
    results: dict[str, str] = {}
    for t in topics:
        print(f"\n=== {t} ===")
        try:
            results[t] = _one(args.date, t, env, args.dry_run)
        except Exception as e:
            results[t] = f"ERROR: {e}"
        print(f"  → {results[t]}")

    print("\n" + "=" * 64)
    for k, v in results.items():
        print(f"  {k:36s} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
