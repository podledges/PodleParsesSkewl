"""Parse caption/transcript sidecars into a Transcript."""

from __future__ import annotations

import json
import re
from pathlib import Path

from podleparsesskewl.document import Cue, Transcript
from podleparsesskewl.errors import PpsError
from podleparsesskewl.timefmt import parse_clock

SIDECAR_SUFFIXES = (".srt", ".vtt", ".webvtt", ".json")
_ARROW = re.compile(r"\s+-->\s+")
_VTT_TAG = re.compile(r"</?[^>]+>")
_NOTE_OR_STYLE = re.compile(r"^(NOTE|STYLE|REGION)\b")


def discover_sidecar(recording: Path) -> Path | None:
    """Return the first sidecar next to a Recording, if one exists."""
    stem = recording.with_suffix("")
    for suffix in SIDECAR_SUFFIXES:
        candidate = Path(str(stem) + suffix)
        if candidate.is_file():
            return candidate
    return None


def load_sidecar(path: Path) -> Transcript:
    """Load a Transcript from an SRT, VTT, or JSON sidecar."""
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8-sig")
    if suffix == ".srt":
        cues = parse_srt(text)
        source = f"sidecar:srt:{path.name}"
    elif suffix in {".vtt", ".webvtt"}:
        cues = parse_vtt(text)
        source = f"sidecar:vtt:{path.name}"
    elif suffix == ".json":
        cues = parse_json_transcript(text)
        source = f"sidecar:json:{path.name}"
    else:
        raise PpsError(f"unsupported transcript sidecar: {path}")
    return Transcript(cues=tuple(cues), source=source)


def parse_srt(text: str) -> list[Cue]:
    cues: list[Cue] = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip())
    for block in blocks:
        lines = [line for line in block.split("\n") if line.strip() != ""]
        if not lines:
            continue
        timing_index = 0
        if lines[0].strip().isdigit():
            timing_index = 1
        if timing_index >= len(lines):
            continue
        start, end = _parse_range(lines[timing_index])
        body = _join_cue_lines(lines[timing_index + 1 :])
        if body:
            cues.append(Cue(start_seconds=start, end_seconds=end, text=body))
    return cues


def parse_vtt(text: str) -> list[Cue]:
    normalized = text.replace("\r\n", "\n")
    if normalized.lstrip().upper().startswith("WEBVTT"):
        first_break = normalized.find("\n\n")
        normalized = normalized[first_break + 2 :] if first_break != -1 else ""
    cues: list[Cue] = []
    blocks = re.split(r"\n\s*\n", normalized.strip())
    for block in blocks:
        lines = [line for line in block.split("\n") if line.strip() != ""]
        if not lines or _NOTE_OR_STYLE.match(lines[0]):
            continue
        timing_index = 0
        if "-->" not in lines[0] and len(lines) > 1:
            timing_index = 1
        if timing_index >= len(lines) or "-->" not in lines[timing_index]:
            continue
        start, end = _parse_range(lines[timing_index])
        body = _join_cue_lines(lines[timing_index + 1 :])
        body = _VTT_TAG.sub("", body).strip()
        if body:
            cues.append(Cue(start_seconds=start, end_seconds=end, text=body))
    return cues


def parse_json_transcript(text: str) -> list[Cue]:
    payload = json.loads(text)
    raw_cues = payload
    if isinstance(payload, dict):
        raw_cues = payload.get("cues", payload.get("segments", []))
    if not isinstance(raw_cues, list):
        raise PpsError("JSON transcript must be a list of cues or {cues: [...]}")
    cues: list[Cue] = []
    for item in raw_cues:
        if not isinstance(item, dict):
            raise PpsError("each JSON cue must be an object")
        start = _json_seconds(item, "start_seconds", "start")
        end = _json_seconds(item, "end_seconds", "end")
        body = str(item.get("text", "")).strip()
        if body:
            cues.append(Cue(start_seconds=start, end_seconds=end, text=body))
    return cues


def _json_seconds(item: dict, *keys: str) -> float:
    for key in keys:
        if key in item:
            value = item[key]
            if isinstance(value, str):
                return parse_clock(value)
            return float(value)
    raise PpsError(f"JSON cue missing time field ({' / '.join(keys)})")


def _parse_range(line: str) -> tuple[float, float]:
    timing = line.split(" align:")[0].split(" position:")[0].strip()
    parts = _ARROW.split(timing)
    if len(parts) != 2:
        raise PpsError(f"invalid cue timing line: {line!r}")
    return parse_clock(parts[0].strip()), parse_clock(parts[1].strip())


def _join_cue_lines(lines: list[str]) -> str:
    return " ".join(line.strip() for line in lines if line.strip()).strip()
