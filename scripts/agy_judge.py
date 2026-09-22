"""Run the multimodal QC judge through the Antigravity CLI (`agy`).

Why this exists: the judge used to call the paid Gemini API. `agy` runs the
same class of model on the account's own consumer subscription, so the judge
costs nothing. Everything below is the accumulated result of getting that to
work headlessly on the VM -- each rule here was a failure first.

    1. ATTACHMENTS MUST BE ABSOLUTE PATHS. agy's shell cwd is its own scratch
       directory, never the directory you launched it from. Hand it a relative
       `@name.mp3` and it does not fail -- it goes looking, first with
       find_by_name, then `Get-ChildItem -Path C:\\ -Recurse`, i.e. a scan of
       the whole disk. Headless mode auto-denies that command and you get an
       empty response with no error worth reading.

    2. THE PROMPT MUST BE INLINE, NOT `@prompt.txt`. Referencing a text file
       makes agy reach for a file-read tool that needs the same denied
       permission. Inlining 20-30 KB works.

    3. agy STILL NEEDS `read_file(<dir>)` ALLOWED for the attachment directory.
       That is the one permission this requires; see vm/setup_agy.sh.

    4. ONLY A PRO-CLASS MODEL SURVIVES THE FULL PROMPT. Measured 2026-09-07 on
       six episodes: gemini-3.1-pro-high attaches the audio and returns a clean
       verdict, while 3.8/3.7/3.6-flash all abandon the attachment and try to
       shell out (`powershell`, `Get-ChildItem`, `python -c`) once the prompt
       is this long. The flash models CAN hear audio -- they transcribe a short
       probe correctly -- they just lose the thread on a 20 KB instruction.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

# Pro-class is not a preference here, it is the only tier that works; see (4).
DEFAULT_AGY_MODEL = os.environ.get("AGY_JUDGE_MODEL", "gemini-3.1-pro-high")

# A judge call runs 5-10 minutes: it listens to a 25-45 minute episode and
# reads a chapter. agy's own default is 5 minutes, which cuts off mid-verdict.
AGY_TIMEOUT = os.environ.get("AGY_PRINT_TIMEOUT", "25m")

# Belt and braces: --print-timeout should end the run, but a wedged agy would
# otherwise hang the nightly job forever.
_SUBPROCESS_TIMEOUT_S = 2400


def agy_available() -> bool:
    """True when the agy binary exists and is signed in."""
    return _agy_exe() is not None


def _agy_exe() -> str | None:
    exe = shutil.which("agy")
    if exe:
        return exe
    # The installer puts it here and appends PATH to ~/.bashrc, which a cron
    # job never sources.
    #
    # exists() is wrapped because it can RAISE, not just return False: with
    # `sudo -u User -E` the process runs as User while HOME stays /root, so
    # Path.home() resolves to /root/.local/bin/agy and stat() gives
    # PermissionError. That crashed the whole retroactive QC run on
    # 2026-09-14 before it judged a single episode.
    for cand in (Path.home() / ".local/bin/agy",
                 Path("/home/User/.local/bin/agy")):
        try:
            if cand.exists():
                return str(cand)
        except OSError:
            continue
    return None


def _extract_verdict(text: str) -> dict | None:
    """Pull the JSON verdict out of agy's reply.

    gemini-3.1-pro-high sometimes wraps the object in a ```json fence and
    sometimes does not, so both have to work.
    """
    text = (text or "").strip()
    if not text:
        return None
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    start = text.find("{")
    if start == -1:
        return None
    try:
        return json.loads(text[start:text.rfind("}") + 1])
    except json.JSONDecodeError:
        return None


# agy reads an attachment natively most of the time, but it is an agent: now
# and then it decides the file is something to PROCESS rather than something it
# already has, and reaches for a shell. On 2026-09-13/14 it tried
#   cat "…/030 - 26 Youth Suicide.pdf" | pdftotext - -
# on four episodes out of roughly twenty-five. Headless mode auto-denies the
# `command` permission, so the reply came back empty and those episodes went
# unjudged. Allowing pdftotext would only move the problem to the next tool it
# thinks of, so the fix is to tell it plainly that the files are already here.
_NO_TOOLS = (
    "The files above are ATTACHED and already available to you directly: read "
    "the PDF and listen to the audio as attachments. Do NOT run any command, "
    "shell pipeline or tool to open, convert, extract or transcribe them — no "
    "cat, no pdftotext, no ffmpeg. Any such call is denied and you will "
    "produce nothing.\n\n"
)

# Retries, because every way this fails is intermittent rather than a broken
# setup, and the same call usually comes back clean on the next attempt.
#
# Two distinct failures need them. agy sometimes reaches for a shell to
# "process" an attachment and gets denied; and sometimes it simply answers
# without loading the media at all. The second is visible in its own
# conversation store: a run that ingested the audio records five steps and a
# ~56 MB database, one that skipped it records two steps and ~200 KB. No error
# is raised either way — it just answers, confidently, on the text alone.
#
# Three attempts because on 2026-09-15 it happened on two of eight calls; at
# that rate two attempts still leave a few per cent that reach the gate with no
# verdict, and each of those costs a held episode.
_ATTEMPTS = 3


def ask_agy(system: str, user: str, model: str | None = None,
            attempts: int = 2) -> str | None:
    """A plain text completion through agy. Returns the reply, or None.

    Much simpler than the judge: no attachment means no file to find, no
    read permission, and none of the failure modes in the notes above. Used
    for the digests and the QC-trends proposal, which are text in, text out —
    both of which stopped working when the Gemini API key was deleted on
    2026-09-14, for no better reason than that nothing had moved them across.

    The prompt goes in on STDIN, not as `-p`. On 2026-09-20 the clinical-
    questions digest, which quotes 121 articles, died with
    `OSError: [Errno 7] Argument list too long` before agy was even started:
    Linux caps a single argv entry at 128 KB. agy reads a piped prompt the same
    way it reads `-p`, with no such limit. (The judge still uses `-p`: its
    prompt is ~25 KB and its `@path` handling is the fragile part — see (1).)
    """
    exe = _agy_exe()
    if not exe:
        return None
    for _ in range(max(1, attempts)):
        try:
            proc = subprocess.run(
                [exe,
                 "--model", model or DEFAULT_AGY_MODEL,
                 "--print-timeout", AGY_TIMEOUT,
                 "--output-format", "json"],
                input=f"{system}\n\n{user}",
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=_SUBPROCESS_TIMEOUT_S)
            reply = (json.loads(proc.stdout or "{}").get("response") or "").strip()
            if reply:
                return reply
        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            continue
    return None


def judge_with_agy(prompt: str, attachments: list[Path],
                   model: str | None = None) -> tuple[dict | None, str]:
    """One judge call. Returns (verdict, diagnostic) -- verdict is None on
    failure and the diagnostic always says which of the ways it failed, so a
    silent empty reply can never be mistaken for a clean pass."""
    exe = _agy_exe()
    if not exe:
        return None, "agy binary not found (install it, or set PATH)"

    missing = [str(a) for a in attachments if not Path(a).exists()]
    if missing:
        return None, f"attachment missing: {missing}"

    # See (1): absolute, resolved, no symlinks left to guess at.
    refs = " ".join(f"@{Path(a).resolve()}" for a in attachments)
    last = "no attempt made"
    for attempt in range(1, _ATTEMPTS + 1):
        verdict, last = _one_call(exe, refs, prompt, model, attachments)
        if verdict is not None:
            return verdict, (last if attempt == 1
                             else f"{last} (on attempt {attempt})")
    return None, last


def _one_call(exe: str, refs: str, prompt: str, model: str | None,
              attachment_paths: list[Path]) -> tuple[dict | None, str]:
    try:
        proc = subprocess.run(
            [exe, "-p", f"{refs} {_NO_TOOLS}{prompt}",  # see (2): inline prompt
             "--model", model or DEFAULT_AGY_MODEL,
             "--print-timeout", AGY_TIMEOUT,
             "--output-format", "json"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=_SUBPROCESS_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return None, f"agy did not return within {_SUBPROCESS_TIMEOUT_S}s"

    try:
        env = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return None, (f"agy did not return JSON (rc={proc.returncode}): "
                      f"{(proc.stdout or proc.stderr or '')[:200]}")

    # Whatever happens below, the copies agy keeps of this call go away before
    # we return. See _discard_conversation for why that matters.
    cid = env.get("conversation_id")
    try:
        denied = env.get("denied_actions") or []
        reply = (env.get("response") or "").strip()
        if not reply:
            if denied:
                acts = ", ".join(a.get("action", "?") for a in denied)
                return None, (f"agy produced no output; it was denied [{acts}] — "
                              f"it tried to process an attachment with a tool "
                              f"instead of reading it directly.")
            return None, f"agy returned an empty response (status={env.get('status')})"

        verdict = _extract_verdict(reply)
        if verdict is None or verdict.get("accuracy") is None:
            return None, f"could not parse a verdict from: {reply[:200]}"

        took = env.get("duration_seconds") or 0
        usage = env.get("usage") or {}
        seen = usage.get("input_tokens") or 0

        # DID IT ACTUALLY LISTEN? agy sometimes answers confidently having
        # ingested only the text: on 2026-09-15 dulcan-030 was scored 5/5/5 with
        # no discrepancies in 49 seconds on 14,744 input tokens, and published on
        # the strength of it. A verdict reached without hearing the episode is
        # worse than no verdict at all, because nothing downstream can tell the
        # difference.
        audio_bytes = _audio_bytes(attachment_paths)
        if audio_bytes:
            # Primary evidence: agy's own conversation store. The media is
            # written into it, so a run that heard the episode leaves a database
            # about the size of the audio, and one that did not leaves a few
            # hundred KB. Measured on 2026-09-16:
            #     audio heard     20 MB, 32 MB, 37 MB, 92 MB (for 20-91 MB audio)
            #     audio skipped   192 KB, 372 KB
            # A two-orders-of-magnitude gap, independent of episode length and
            # prompt size — which is exactly what the token count below is not.
            conv = _conversation_bytes(cid)
            if conv is not None:
                if conv < audio_bytes * 0.25:
                    return None, (f"agy's conversation holds {conv:,} bytes "
                                  f"against {audio_bytes:,} bytes of audio — the "
                                  f"media never went in. Verdict discarded.")
            else:
                # Fallback when the store cannot be found: the token count, NET
                # of what the text costs by itself. The first version of this
                # check compared the raw total with a third of the audio estimate
                # and forgot the text: the prompt and a chapter PDF cost ~14.7K
                # tokens with no audio at all, so a 45.9 MB regeneration of
                # dulcan-030 sailed through at 14,711 tokens against a 14,370 bar
                # and was published unheard on 2026-09-16.
                text = _text_tokens_estimate(prompt, attachment_paths)
                expected = _expected_audio_tokens(attachment_paths)
                if seen < text + expected * 0.3:
                    return None, (f"agy answered on {seen:,} input tokens; the "
                                  f"text alone is ~{text:,} and the audio should "
                                  f"add ~{expected:,} — it did not listen. "
                                  f"Verdict discarded.")

        return verdict, f"ok in {took:.0f}s, {seen} input tokens"
    finally:
        _discard_conversation(cid)


def _audio_bytes(paths: list[Path]) -> int:
    total = 0
    for p in paths:
        try:
            if Path(p).suffix.lower() in _AUDIO_SUFFIXES:
                total += Path(p).stat().st_size
        except OSError:
            continue
    return total


def _conversation_bytes(conversation_id: str | None) -> int | None:
    """Size of agy's store for this conversation, or None if it is not found."""
    if not conversation_id:
        return None
    for home in (Path.home(), Path("/home/User")):
        db = home / ".gemini/antigravity-cli/conversations" / f"{conversation_id}.db"
        try:
            if db.exists():
                return db.stat().st_size
        except OSError:
            continue
    return None


# How long a conversation agy left behind is allowed to sit before the next
# judge call sweeps it up. Long enough to still be there when a run is being
# investigated the next morning, short enough that a few days of episodes
# cannot fill the disk.
_STALE_CONVERSATION_DAYS = 2


def _discard_conversation(conversation_id: str | None) -> None:
    """Delete agy's copy of one judge call, and any stale ones left behind.

    agy keeps the whole call on disk — the episode's audio and the chapter PDF —
    under conversations/<id>.db and brain/<id>/. At 20-90 MB per episode that
    reached 8.6 GB by 2026-09-17 and filled the VM's 20 GB disk, which broke the
    next judge call (agy returned an empty response), Chrome Remote Desktop, and
    anything else that needed a temporary file. The verdict itself is already in
    the repository, so once the listen check above has read the size, the copy
    has served its purpose.
    """
    for home in (Path.home(), Path("/home/User")):
        root = home / ".gemini/antigravity-cli"
        convs, brains = root / "conversations", root / "brain"
        try:
            if not convs.is_dir():
                continue
        except OSError:
            continue
        if conversation_id:
            _rm(convs / f"{conversation_id}.db")
            _rm(brains / conversation_id)
        # A crash, a timeout or an older build leaves stores nothing will ever
        # delete, so sweep those too rather than trusting every path to clean up
        # after itself.
        cutoff = time.time() - _STALE_CONVERSATION_DAYS * 86400
        for parent in (convs, brains):
            try:
                entries = list(parent.iterdir())
            except OSError:
                continue
            for entry in entries:
                try:
                    if entry.stat().st_mtime < cutoff:
                        _rm(entry)
                except OSError:
                    continue
        return


def _rm(path: Path) -> None:
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
    except OSError:
        pass


def _text_tokens_estimate(prompt: str, paths: list[Path]) -> int:
    """Deliberately generous guess at what the non-audio input costs, so the
    fallback errs toward discarding a doubtful verdict. ~3 characters per token
    for the Hebrew/English prompt; ~18 bytes per token for a chapter PDF, which
    is what put the book project's text-only calls at ~14.7K."""
    total = len(prompt) // 3
    for p in paths:
        try:
            if Path(p).suffix.lower() not in _AUDIO_SUFFIXES:
                total += Path(p).stat().st_size // 18
        except OSError:
            continue
    return total


_AUDIO_SUFFIXES = (".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac")
# Measured across both projects: NotebookLM audio runs a near-constant
# 1.84 MB/minute, which makes file size a usable proxy for duration.
_MB_PER_MINUTE = 1.84
_TOKENS_PER_AUDIO_SECOND = 32


def _expected_audio_tokens(paths: list[Path]) -> int:
    """Roughly what the attached audio alone should cost in input tokens."""
    total = 0
    for p in paths:
        try:
            if Path(p).suffix.lower() not in _AUDIO_SUFFIXES:
                continue
            minutes = Path(p).stat().st_size / (_MB_PER_MINUTE * 1024 * 1024)
            total += int(minutes * 60 * _TOKENS_PER_AUDIO_SECOND)
        except OSError:
            continue
    return total
