"""End-to-end parse: Recording in, Lecture Document and plain views out."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from podleparsesskewl.align import align_cues_to_stills
from podleparsesskewl.deps import Environment, inspect_environment
from podleparsesskewl.document import LectureDocument, SourceInfo, Still, still_id, still_image_name
from podleparsesskewl.errors import PpsError
from podleparsesskewl.media import extract_still_png, probe_recording, sample_signatures
from podleparsesskewl.report import write_plain_views
from podleparsesskewl.stills import (
    DEFAULT_CHANGE_RATIO,
    DEFAULT_MIN_HOLD_SECONDS,
    DEFAULT_SAMPLE_FPS,
    FrameSignature,
    segment_stills,
)
from podleparsesskewl.transcribe import load_transcript


@dataclass(frozen=True)
class ParseOptions:
    output_dir: Path
    title: str | None = None
    sidecar: Path | None = None
    sample_fps: float = DEFAULT_SAMPLE_FPS
    change_ratio: float = DEFAULT_CHANGE_RATIO
    min_hold_seconds: float = DEFAULT_MIN_HOLD_SECONDS
    keep_work: bool = False


@dataclass(frozen=True)
class ParseResult:
    document: LectureDocument
    document_path: Path
    html_path: Path
    markdown_path: Path


def parse_recording(
    recording: Path,
    options: ParseOptions,
    env: Environment | None = None,
) -> ParseResult:
    """Process one MP4 into a Lecture Document and the plain HTML/Markdown views."""
    recording = recording.resolve()
    if not recording.is_file():
        raise PpsError(f"Recording not found: {recording}")
    environment = env if env is not None else inspect_environment()
    if not environment.can_parse_video:
        raise PpsError(
            "ffmpeg and ffprobe are required to parse a Recording. "
            "Install ffmpeg, or set PODLEPARSESSKEWL_FFMPEG / PODLEPARSESSKEWL_FFPROBE."
        )

    output_dir = options.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir = output_dir / "_work"
    work_dir.mkdir(parents=True, exist_ok=True)

    probe = probe_recording(recording, environment)
    if not probe.has_video:
        raise PpsError(f"Recording has no video stream: {recording}")

    transcript = load_transcript(
        recording,
        environment,
        sidecar=options.sidecar,
        work_dir=work_dir,
    )
    frames = sample_signatures(
        recording,
        work_dir,
        environment,
        fps=options.sample_fps,
    )
    duration_seconds = _effective_duration(probe.duration_seconds, frames, options.sample_fps)
    intervals = segment_stills(
        frames,
        duration_seconds=duration_seconds,
        change_ratio=options.change_ratio,
        min_hold_seconds=options.min_hold_seconds,
    )

    stills: list[Still] = []
    for index, interval in enumerate(intervals, start=1):
        image_rel = still_image_name(index)
        image_path = output_dir / image_rel
        extract_still_png(
            recording,
            interval.representative_seconds,
            image_path,
            environment,
        )
        stills.append(
            Still(
                id=still_id(index),
                index=index,
                start_seconds=interval.start_seconds,
                end_seconds=interval.end_seconds,
                image=image_rel.replace("\\", "/"),
            )
        )

    sections = align_cues_to_stills(transcript.cues, stills)
    title = options.title if options.title else recording.stem
    document = LectureDocument(
        title=title,
        source=SourceInfo(
            recording=str(recording),
            duration_seconds=duration_seconds,
            transcript_source=transcript.source,
            width=probe.width,
            height=probe.height,
        ),
        stills=tuple(stills),
        transcript=transcript,
        sections=tuple(sections),
    )
    document_path = write_document(document, output_dir)
    html_path, markdown_path = write_plain_views(document, output_dir)
    if not options.keep_work:
        shutil.rmtree(work_dir, ignore_errors=True)
    return ParseResult(
        document=document,
        document_path=document_path,
        html_path=html_path,
        markdown_path=markdown_path,
    )


def _effective_duration(
    probed_seconds: float,
    frames: list[FrameSignature],
    fps: float,
) -> float:
    """Fall back to the sampled frames when ffprobe reports no usable duration."""
    if probed_seconds > 0:
        return probed_seconds
    if not frames:
        return 0.0
    step = 1.0 / fps if fps > 0 else 0.0
    return frames[-1].time_seconds + step


def copy_still_images(
    document: LectureDocument,
    source_dir: Path,
    output_dir: Path,
) -> list[str]:
    """Copy each Still image next to a relocated Document; return missing ones."""
    if source_dir.resolve() == output_dir.resolve():
        return []
    missing: list[str] = []
    for still in document.stills:
        reference = still.image
        if not reference:
            continue
        relative = PurePosixPath(reference)
        if relative.is_absolute() or PureWindowsPath(reference).is_absolute():
            continue
        if ".." in relative.parts:
            raise PpsError(f"Still image path escapes the Lecture folder: {reference}")
        source = source_dir / Path(*relative.parts)
        if not source.is_file():
            missing.append(reference)
            continue
        destination = output_dir / Path(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    return missing


def write_document(document: LectureDocument, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "lecture.json"
    path.write_text(
        json.dumps(document.to_json_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def load_document(path: Path) -> LectureDocument:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PpsError(f"could not read Lecture Document {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PpsError(f"Lecture Document {path} must be a JSON object")
    try:
        return LectureDocument.from_json_dict(payload)
    except PpsError as exc:
        raise PpsError(f"{path}: {exc}") from exc


def default_output_dir(recording: Path) -> Path:
    return recording.resolve().parent / f"{recording.stem}.lecture"
