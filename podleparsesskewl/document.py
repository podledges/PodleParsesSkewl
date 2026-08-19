"""Canonical Lecture Document: stills, transcript, and said-to-shown links."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from podleparsesskewl.errors import PpsError

SCHEMA_V1 = "podleparsesskewl.lecture/v1"


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
        """Build a Document from parsed JSON, reporting bad shapes as PpsError."""
        try:
            source = SourceInfo(**payload["source"])
            stills = tuple(Still(**item) for item in payload["stills"])
            cues = tuple(Cue(**item) for item in payload["transcript"]["cues"])
            transcript = Transcript(cues=cues, source=payload["transcript"]["source"])
            sections = tuple(
                Section(
                    still_id=item["still_id"],
                    said=item["said"],
                    cue_indexes=tuple(item.get("cue_indexes", ())),
                )
                for item in payload["sections"]
            )
            return cls(
                schema=payload.get("schema", SCHEMA_V1),
                title=payload["title"],
                source=source,
                stills=stills,
                transcript=transcript,
                sections=sections,
            )
        except KeyError as exc:
            raise PpsError(
                f"Lecture Document is missing the required field {exc.args[0]!r}"
            ) from exc
        except (TypeError, ValueError) as exc:
            raise PpsError(f"Lecture Document has an invalid field: {exc}") from exc


def still_id(index: int) -> str:
    return f"still-{index:03d}"


def still_image_name(index: int) -> str:
    return f"stills/{still_id(index)}.png"
