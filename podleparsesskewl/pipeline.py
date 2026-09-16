"""End-to-end parse: Recording in, Lecture Document and plain views out."""

from __future__ import annotations

import json
import shutil
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Callable

from podleparsesskewl.align import align_cues_to_stills
from podleparsesskewl.deps import Environment, inspect_environment
from podleparsesskewl.document import LectureDocument, SourceInfo, Still, still_id, still_image_name
from podleparsesskewl.errors import PpsError, writing
from podleparsesskewl.media import extract_audio_wav, extract_stills_png, probe_recording, sample_signatures
from podleparsesskewl.report import (
    DEFAULT_PARAGRAPH_WORDS,
    DEFAULT_PAUSE_SECONDS,
    group_transcript,
    write_plain_views,
    write_transcript_view,
)
from podleparsesskewl.stills import (
    DEFAULT_CHANGE_RATIO,
    DEFAULT_MIN_HOLD_SECONDS,
    DEFAULT_SAMPLE_FPS,
    FrameSignature,
    segment_stills,
)
from podleparsesskewl.transcribe import TranscriptionOptions, load_transcript

WORK_PREFIX = "_work-"


@dataclass(frozen=True)
class ParseOptions:
    output_dir: Path
    title: str | None = None
    sidecar: Path | None = None
    sample_fps: float = DEFAULT_SAMPLE_FPS
    change_ratio: float = DEFAULT_CHANGE_RATIO
    min_hold_seconds: float = DEFAULT_MIN_HOLD_SECONDS
    keep_work: bool = False
    visual_lookback_seconds: float | None = None
    pause_seconds: float = DEFAULT_PAUSE_SECONDS
    paragraph_words: int = DEFAULT_PARAGRAPH_WORDS
    transcription: TranscriptionOptions = TranscriptionOptions()


@dataclass(frozen=True)
class ParseResult:
    document: LectureDocument
    document_path: Path
    html_path: Path
    markdown_path: Path

    @property
    def transcript_path(self) -> Path:
        return self.document_path.parent / "transcript.md"


def parse_recording(
    recording: Path,
    options: ParseOptions,
    env: Environment | None = None,
    progress: Callable[[str], None] | None = None,
) -> ParseResult:
    """Process one MP4 into a Lecture Document and the plain HTML/Markdown views."""
    notify = progress or (lambda _phase: None)
    notify("checking")
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
    with writing(f"the Lecture folder {output_dir}"):
        output_dir.mkdir(parents=True, exist_ok=True)
        work_dir = Path(tempfile.mkdtemp(prefix=WORK_PREFIX, dir=output_dir))

    try:
        probe = probe_recording(recording, environment)
        if not probe.has_video and not probe.has_audio and options.sidecar is None:
            raise PpsError(f"Recording has no usable audio or moving video stream: {recording}")

        notify("processing")
        transcript = load_transcript(
            recording,
            environment,
            sidecar=options.sidecar,
            work_dir=work_dir,
            has_audio=probe.has_audio,
            transcription=options.transcription,
        )
        frames = (
            sample_signatures(
                recording,
                work_dir,
                environment,
                fps=options.sample_fps,
            )
            if probe.has_video
            else []
        )
        duration_seconds = _effective_duration(
            probe.duration_seconds, frames, options.sample_fps
        )
        if duration_seconds <= 0 and probe.has_audio and not probe.has_video:
            wav = work_dir / "audio.wav"
            if not wav.is_file():
                extract_audio_wav(recording, wav, environment)
            with wave.open(str(wav), "rb") as audio:
                duration_seconds = audio.getnframes() / audio.getframerate()
        intervals = (
            segment_stills(
                frames,
                duration_seconds=duration_seconds,
                change_ratio=options.change_ratio,
                min_hold_seconds=options.min_hold_seconds,
                lookback_seconds=options.visual_lookback_seconds,
            )
            if probe.has_video
            else []
        )

        if intervals:
            extract_stills_png(
                recording,
                [interval.representative_seconds for interval in intervals],
                output_dir,
                work_dir,
                environment,
                fps=options.sample_fps,
            )
        stills: list[Still] = []
        for index, interval in enumerate(intervals, start=1):
            image_rel = still_image_name(index)
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
        notify("validating")
        group_transcript(
            transcript.cues,
            pause_seconds=options.pause_seconds,
            max_words=options.paragraph_words,
            visual_boundaries=tuple(still.start_seconds for still in stills[1:]),
        )
        document_path = write_document(document, output_dir)
        html_path, markdown_path = write_plain_views(document, output_dir)
        write_transcript_view(
            document,
            output_dir,
            pause_seconds=options.pause_seconds,
            max_words=options.paragraph_words,
        )
    finally:
        if not options.keep_work:
            shutil.rmtree(work_dir, ignore_errors=True)
    notify("done")
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
    """Copy each Still image next to a relocated Document.

    Returns one message per reference that could not be made local, so the
    caller can say why a copied view would show a broken image.
    """
    if source_dir.resolve() == output_dir.resolve():
        return []
    problems: list[str] = []
    for still in document.stills:
        reference = still.image
        if not reference:
            problems.append(
                f"{still.id} has no image reference, so the copied view will show a broken image"
            )
            continue
        relative = PurePosixPath(reference)
        windows = PureWindowsPath(reference)
        if relative.is_absolute() or windows.is_absolute() or windows.drive:
            problems.append(
                f"{reference} is an absolute path, so it was not copied into {output_dir}; "
                "the rendered view still points at the original location"
            )
            continue
        if ".." in relative.parts or ".." in windows.parts:
            raise PpsError(f"Still image path escapes the Lecture folder: {reference}")
        source = source_dir / Path(*relative.parts)
        if not source.is_file():
            problems.append(f"{reference} was not found in {source_dir}, so the copied view will show a broken image")
            continue
        destination = output_dir / Path(*relative.parts)
        if not _inside(destination, output_dir):
            raise PpsError(f"Still image path escapes the Lecture folder: {reference}")
        with writing(f"Still image {destination}"):
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    return problems


def _inside(candidate: Path, folder: Path) -> bool:
    root = folder.resolve()
    return root == candidate.resolve() or root in candidate.resolve().parents


def write_document(document: LectureDocument, output_dir: Path) -> Path:
    path = output_dir / "lecture.json"
    try:
        text = json.dumps(
            document.to_json_dict(),
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
    except ValueError as exc:
        raise PpsError(
            f"refusing to write {path}: the Lecture holds a number that is not valid JSON ({exc})"
        ) from exc
    with writing(f"the Lecture Document {path}"):
        output_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
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
