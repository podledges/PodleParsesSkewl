"""Canonical Lecture Document: stills, transcript, and said-to-shown links."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from podleparsesskewl.errors import PpsError

SCHEMA_V1 = "podleparsesskewl.lecture/v1"
_COUNT_LIMIT = 10**12


@dataclass(frozen=True)
class Cue:
    """A timed span of spoken text."""

    start_seconds: float
    end_seconds: float
    text: str


@dataclass(frozen=True)
class Transcript:
    """Timed speech text of one Recording, however it was obtained."""

    cues: tuple[Cue, ...]
    source: str


@dataclass(frozen=True)
class Still:
    """A visually stable interval plus the representative image taken from it."""

    id: str
    index: int
    start_seconds: float
    end_seconds: float
    image: str


@dataclass(frozen=True)
class Section:
    """One Still paired with the Said that belongs to its interval."""

    still_id: str
    said: str
    cue_indexes: tuple[int, ...]


@dataclass(frozen=True)
class SourceInfo:
    recording: str
    duration_seconds: float
    transcript_source: str
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class LectureDocument:
    """Structured result of one Lecture: stills, transcript, and their links."""

    title: str
    source: SourceInfo
    stills: tuple[Still, ...]
    transcript: Transcript
    sections: tuple[Section, ...]
    schema: str = SCHEMA_V1

    def to_json_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload

    @classmethod
    def from_json_dict(cls, payload: dict[str, Any]) -> LectureDocument:
        """Build a Document from parsed JSON, reporting bad shapes as PpsError.

        This is the one boundary every Document enters through, so field types
        are checked here rather than trusted by the renderers downstream.
        """
        try:
            raw_source = _as_object(payload["source"], "source")
            source = SourceInfo(
                recording=_as_text(raw_source["recording"], "source.recording"),
                duration_seconds=_as_seconds(
                    raw_source["duration_seconds"], "source.duration_seconds"
                ),
                transcript_source=_as_text(
                    raw_source["transcript_source"], "source.transcript_source"
                ),
                width=_as_optional_count(raw_source.get("width"), "source.width"),
                height=_as_optional_count(raw_source.get("height"), "source.height"),
            )
            stills = tuple(
                Still(
                    id=_as_text(item["id"], f"stills[{position}].id"),
                    index=_as_count(item["index"], f"stills[{position}].index"),
                    start_seconds=_as_seconds(
                        item["start_seconds"], f"stills[{position}].start_seconds"
                    ),
                    end_seconds=_as_seconds(
                        item["end_seconds"], f"stills[{position}].end_seconds"
                    ),
                    image=_as_text(item["image"], f"stills[{position}].image"),
                )
                for position, item in enumerate(
                    _as_objects(payload["stills"], "stills")
                )
            )
            raw_transcript = _as_object(payload["transcript"], "transcript")
            cues = tuple(
                Cue(
                    start_seconds=_as_seconds(
                        item["start_seconds"], f"transcript.cues[{position}].start_seconds"
                    ),
                    end_seconds=_as_seconds(
                        item["end_seconds"], f"transcript.cues[{position}].end_seconds"
                    ),
                    text=_as_text(item["text"], f"transcript.cues[{position}].text"),
                )
                for position, item in enumerate(
                    _as_objects(raw_transcript["cues"], "transcript.cues")
                )
            )
            transcript = Transcript(
                cues=cues,
                source=_as_text(raw_transcript["source"], "transcript.source"),
            )
            sections = tuple(
                Section(
                    still_id=_as_text(item["still_id"], f"sections[{position}].still_id"),
                    said=_as_text(item["said"], f"sections[{position}].said"),
                    cue_indexes=tuple(
                        _as_count(value, f"sections[{position}].cue_indexes[{at}]")
                        for at, value in enumerate(
                            _as_list(item.get("cue_indexes", ()), f"sections[{position}].cue_indexes")
                        )
                    ),
                )
                for position, item in enumerate(
                    _as_objects(payload["sections"], "sections")
                )
            )
            return cls(
                schema=_as_text(payload.get("schema", SCHEMA_V1), "schema"),
                title=_as_text(payload["title"], "title"),
                source=source,
                stills=stills,
                transcript=transcript,
                sections=sections,
            )
        except KeyError as exc:
            raise PpsError(
                f"Lecture Document is missing the required field {exc.args[0]!r}"
            ) from exc
        except (TypeError, ValueError, ArithmeticError) as exc:
            raise PpsError(f"Lecture Document has an invalid field: {exc}") from exc


def _as_text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise PpsError(f"Lecture Document field {field} must be text, got {_kind(value)}")
    return value


def finite_seconds(value: Any, label: str) -> float:
    """Coerce a time to a finite float, the invariant every Document number holds.

    Applied on the way in and on the way out, so the program can never write a
    Lecture Document it would then refuse to read.
    """
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise PpsError(f"{label} is not a number of seconds: {value!r}") from exc
    if not math.isfinite(number):
        raise PpsError(f"{label} must be a finite number of seconds, got {value!r}")
    return number


def _as_seconds(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise PpsError(
            f"Lecture Document field {field} must be a number of seconds, got {_kind(value)}"
        )
    return finite_seconds(value, f"Lecture Document field {field}")


def _as_count(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise PpsError(
            f"Lecture Document field {field} must be a whole number, got {_kind(value)}"
        )
    try:
        number = int(value)
    except (ValueError, OverflowError) as exc:
        raise PpsError(
            f"Lecture Document field {field} is not a whole number: {value!r}"
        ) from exc
    if abs(number) > _COUNT_LIMIT:
        raise PpsError(
            f"Lecture Document field {field} is out of range: {value!r}"
        )
    return number


def _as_optional_count(value: Any, field: str) -> int | None:
    return None if value is None else _as_count(value, field)


def _as_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PpsError(f"Lecture Document field {field} must be an object, got {_kind(value)}")
    return value


def _as_list(value: Any, field: str) -> list[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise PpsError(f"Lecture Document field {field} must be a list, got {_kind(value)}")
    return list(value)


def _as_objects(value: Any, field: str) -> list[dict[str, Any]]:
    return [
        _as_object(item, f"{field}[{position}]")
        for position, item in enumerate(_as_list(value, field))
    ]


def _kind(value: Any) -> str:
    return "null" if value is None else type(value).__name__


def still_id(index: int) -> str:
    return f"still-{index:03d}"


def still_image_name(index: int) -> str:
    return f"stills/{still_id(index)}.png"
