"""Clock-time parsing and formatting."""

from __future__ import annotations

import re

_CLOCK = re.compile(
    r"^(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?$"
)


def parse_clock(value: str) -> float:
    """Parse `HH:MM:SS.mmm`, `MM:SS.mmm`, SRT commas, or VTT dots into seconds."""
    match = _CLOCK.match(value.strip())
    if not match:
        raise ValueError(f"not a clock timestamp: {value!r}")
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    fraction = match.group(4) or "0"
    millis = int(fraction.ljust(3, "0")[:3])
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0


def format_clock(seconds: float) -> str:
    """Format seconds as `HH:MM:SS`."""
    total = int(max(0.0, seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_clock_ms(seconds: float) -> str:
    """Format seconds as `HH:MM:SS.mmm`."""
    if seconds < 0:
        seconds = 0.0
    whole = int(seconds)
    millis = int(round((seconds - whole) * 1000))
    if millis == 1000:
        whole += 1
        millis = 0
    hours, rem = divmod(whole, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"
