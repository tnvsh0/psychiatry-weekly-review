#!/usr/bin/env python3
"""
Episode duration for the audio NotebookLM actually returns.

The files are named .mp3 and the feed declares audio/mpeg, but NotebookLM
returns FRAGMENTED MPEG-4 (ftyp brand `dash`): a tiny init `moov` with no
sample table, then `sidx` + repeated `moof`/`mdat`. Consequences:

  * mutagen.mp3.MP3()  -> HeaderNotFoundError "can't sync to MPEG frame"
  * mutagen.File()     -> recognises MP4 but reports length == 0, because a
                          fragmented file carries no duration in its header.

which is why <itunes:duration> was essentially never emitted.

The duration IS recoverable: the `sidx` (segment index) lists every subsegment's
duration in a known timescale, and they sum to the total. That is how a DASH
player computes length, and it needs no ffmpeg — just the first few KB of the
file, so a remote episode can be measured with one HTTP range request.

    from audio_duration import duration_seconds, duration_from_url
"""

from __future__ import annotations

import struct
from pathlib import Path

_PROBE_BYTES = 65536  # sidx sits right after ftyp+moov; 64 KB is ample


def _sidx_duration(buf: bytes) -> int | None:
    """Sum the sidx subsegment durations. None if there is no usable sidx."""
    i = buf.find(b"sidx")
    if i < 0:
        return None
    try:
        p = i + 4
        version = buf[p]
        p += 4                                   # version(1) + flags(3)
        p += 4                                   # reference_ID
        timescale = struct.unpack(">I", buf[p:p + 4])[0]
        p += 4
        p += 8 if version == 0 else 16           # earliest_pres_time + first_offset
        p += 2                                   # reserved
        count = struct.unpack(">H", buf[p:p + 2])[0]
        p += 2
        total = 0
        for _ in range(count):
            p += 4                               # reference_type(1b) + size(31b)
            total += struct.unpack(">I", buf[p:p + 4])[0]
            p += 4
            p += 4                               # SAP flags
        if not timescale or not total:
            return None
        return int(total / timescale)
    except Exception:
        return None


def duration_seconds(path: str | Path) -> int | None:
    """Duration of a local episode file, or None if it cannot be determined."""
    try:
        with open(path, "rb") as f:
            buf = f.read(_PROBE_BYTES)
    except Exception:
        return None
    d = _sidx_duration(buf)
    if d:
        return d
    # Fall back to mutagen for anything that really is a normal audio file.
    try:
        import mutagen
        m = mutagen.File(str(path))
        if m is not None and getattr(m.info, "length", 0):
            return int(m.info.length)
    except Exception:
        pass
    return None


def duration_from_url(url: str, timeout: int = 45) -> int | None:
    """Duration of a published episode, fetching only its first bytes."""
    try:
        import requests
        r = requests.get(url, headers={"Range": f"bytes=0-{_PROBE_BYTES - 1}"},
                         timeout=timeout)
        return _sidx_duration(r.content)
    except Exception:
        return None


if __name__ == "__main__":
    import sys
    for a in sys.argv[1:]:
        d = duration_from_url(a) if a.startswith("http") else duration_seconds(a)
        print(f"{d if d is not None else 'unknown'}  {a}")
