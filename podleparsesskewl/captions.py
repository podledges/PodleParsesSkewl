"""Parse caption/transcript sidecars into a Transcript."""

from __future__ import annotations

import json
import re
from pathlib import Path

from podleparsesskewl.document import SCHEMA_V1, Cue, Transcript
from podleparsesskewl.errors import PpsError
from podleparsesskewl.timefmt import parse_clock

SIDECAR_SUFFIXES = (".srt", ".vtt", ".webvtt", ".json")
_ARROW = re.compile(r"\s+-->\s+")
_VTT_TAG = re.compile(r"</?[^>]+>")
_NOTE_OR_STYLE = re.compile(r"^(NOTE|STYLE|REGION)\b")
_DOCUMENT_NOT_SIDECAR = (
    "this is a PodleParsesSkewl Lecture Document, not a caption sidecar. "
    "Use `pps render` to rebuild its views, or point --transcript at a "
    ".srt/.vtt/.json caption file"
)


def discover_sidecar(recording: Path) -> Path | None:
    """Return the first caption sidecar next to a Recording, if one exists.

    A `lecture.json` Lecture Document sits at the same path a JSON sidecar
    would, so it is skipped rather than mistaken for its own input.
    """
    stem = recording.with_suffix("")
    for suffix in SIDECAR_SUFFIXES:
        candidate = Path(str(stem) + suffix)
        if not candidate.is_file():
            continue
        if suffix == ".json" and _looks_like_document(candidate):
            continue
        return candidate
    return None


def load_sidecar(path: Path) -> Transcript:
    """Load a Transcript from an SRT, VTT, or JSON sidecar."""
    suffix = path.suffix.lower()
    if suffix not in SIDECAR_SUFFIXES:
        raise PpsError(f"unsupported transcript sidecar: {path}")
    text = _read_sidecar_text(path)
    try:
        if suffix == ".srt":
            cues = parse_srt(text)
            source = f"sidecar:srt:{path.name}"
        elif suffix == ".json":
            cues = parse_json_transcript(text)
            source = f"sidecar:json:{path.name}"
        else:
            cues = parse_vtt(text)
            source = f"sidecar:vtt:{path.name}"
    except PpsError as exc:
        raise PpsError(f"{path}: {exc}") from exc
    except (TypeError, ValueError) as exc:
        raise PpsError(f"could not parse transcript sidecar {path}: {exc}") from exc
    if not cues:
        raise PpsError(
            f"caption sidecar {path} is empty or invalid: it yielded no cues. A sidecar "
            "always wins over audio, so this Recording is not transcribed while the file "
            "is there. Replace it with a caption file that has timed text, or remove it "
            "to transcribe the audio instead."
        )
    return Transcript(cues=tuple(cues), source=source)


def _looks_like_document(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and _is_document_payload(payload)


def _is_document_payload(payload: dict) -> bool:
    if payload.get("schema") == SCHEMA_V1:
        return True
    return "stills" in payload and "sections" in payload and "transcript" in payload


def _read_sidecar_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PpsError(
            f"transcript sidecar {path} is not UTF-8 text ({exc.reason} at byte {exc.start}). "
            "Re-save it as UTF-8 and retry."
        ) from exc
    except OSError as exc:
        raise PpsError(f"could not read transcript sidecar {path}: {exc}") from exc


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
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PpsError(f"invalid JSON transcript: {exc}") from exc
    raw_cues = payload
    if isinstance(payload, dict):
        if _is_document_payload(payload):
            raise PpsError(_DOCUMENT_NOT_SIDECAR)
        for key in ("cues", "segments"):
            if key in payload:
                raw_cues = payload[key]
                break
        else:
            keys = ", ".join(sorted(str(key) for key in payload)) or "none"
            raise PpsError(
                "JSON transcript object must hold a 'cues' or 'segments' list "
                f"(top-level keys: {keys})"
            )
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
            try:
                if isinstance(value, str):
                    return parse_clock(value)
                return float(value)
            except (TypeError, ValueError) as exc:
                raise PpsError(f"JSON cue has an invalid {key} value {value!r}") from exc
    raise PpsError(f"JSON cue missing time field ({' / '.join(keys)})")


def _parse_range(line: str) -> tuple[float, float]:
    timing = line.split(" align:")[0].split(" position:")[0].strip()
    parts = _ARROW.split(timing)
    if len(parts) != 2:
        raise PpsError(f"invalid cue timing line: {line!r}")
    try:
        return parse_clock(parts[0].strip()), parse_clock(parts[1].strip())
    except ValueError as exc:
        raise PpsError(f"invalid cue timing line: {line!r} ({exc})") from exc


def _join_cue_lines(lines: list[str]) -> str:
    return " ".join(line.strip() for line in lines if line.strip()).strip()
