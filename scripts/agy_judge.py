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

# One retry, because the failure is a sampling accident rather than a broken
# setup: the same call usually attaches cleanly on the next attempt.
_ATTEMPTS = 2


def ask_agy(system: str, user: str, model: str | None = None,
            attempts: int = 2) -> str | None:
    """A plain text completion through agy. Returns the reply, or None.

    Much simpler than the judge: no attachment means no file to find, no
    read permission, and none of the failure modes in the notes above. Used
    for the digests and the QC-trends proposal, which are text in, text out —
    both of which stopped working when the Gemini API key was deleted on
    2026-09-14, for no better reason than that nothing had moved them across.
    """
    exe = _agy_exe()
    if not exe:
        return None
    for _ in range(max(1, attempts)):
        try:
            proc = subprocess.run(
                [exe, "-p", f"{system}\n\n{user}",
                 "--model", model or DEFAULT_AGY_MODEL,
                 "--print-timeout", AGY_TIMEOUT,
                 "--output-format", "json"],
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
        verdict, last = _one_call(exe, refs, prompt, model)
        if verdict is not None:
            return verdict, (last if attempt == 1
                             else f"{last} (on attempt {attempt})")
    return None, last


def _one_call(exe: str, refs: str, prompt: str,
              model: str | None) -> tuple[dict | None, str]:
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
    return verdict, (f"ok in {took:.0f}s, {usage.get('input_tokens', 0)} input tokens")
