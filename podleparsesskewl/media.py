"""ffmpeg/ffprobe adapters for probing, sampling, and extracting Stills."""

from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

from podleparsesskewl.deps import Environment
from podleparsesskewl.errors import PpsError, writing
from podleparsesskewl.stills import (
    DEFAULT_SAMPLE_FPS,
    DEFAULT_SAMPLE_HEIGHT,
    DEFAULT_SAMPLE_WIDTH,
    FrameSignature,
)


@dataclass(frozen=True)
class Probe:
    duration_seconds: float
    width: int | None
    height: int | None
    has_audio: bool
    has_video: bool


def probe_recording(path: Path, env: Environment) -> Probe:
    if not env.ffprobe.found or env.ffprobe.path is None:
        raise PpsError("ffprobe is required to read a Recording")
    command = [
        str(env.ffprobe.path),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    result = _run(command, "ffprobe")
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise PpsError(f"ffprobe returned invalid JSON for {path}") from exc
    fmt = payload.get("format") or {}
    duration = _optional_seconds(fmt.get("duration")) or 0.0
    width = None
    height = None
    has_audio = False
    has_video = False
    for stream in payload.get("streams") or []:
        kind = stream.get("codec_type")
        if kind == "video" and (stream.get("disposition") or {}).get("attached_pic") != 1:
            has_video = True
            if stream.get("width"):
                width = int(stream["width"])
            if stream.get("height"):
                height = int(stream["height"])
            if duration == 0.0:
                duration = _optional_seconds(stream.get("duration")) or 0.0
        elif kind == "audio":
            has_audio = True
            if duration == 0.0:
                duration = _optional_seconds(stream.get("duration")) or 0.0
    return Probe(
        duration_seconds=duration,
        width=width,
        height=height,
        has_audio=has_audio,
        has_video=has_video,
    )


def _optional_seconds(value: object) -> float | None:
    """Read an ffprobe duration field, tolerating absent or "N/A" values."""
    if value is None:
        return None
    try:
        seconds = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return seconds


def sample_signatures(
    recording: Path,
    work_dir: Path,
    env: Environment,
    *,
    fps: float = DEFAULT_SAMPLE_FPS,
    width: int = DEFAULT_SAMPLE_WIDTH,
    height: int = DEFAULT_SAMPLE_HEIGHT,
) -> list[FrameSignature]:
    if not env.ffmpeg.found or env.ffmpeg.path is None:
        raise PpsError("ffmpeg is required to sample frames from a Recording")
    with writing(f"the work folder {work_dir}"):
        work_dir.mkdir(parents=True, exist_ok=True)
    raw_path = work_dir / "signatures.gray"
    command = [
        str(env.ffmpeg.path),
        "-v",
        "error",
        "-i",
        str(recording),
        "-vf",
        f"{_sampling_filter(fps)},scale={width}:{height}:flags=fast_bilinear,format=gray",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "-y",
        str(raw_path),
    ]
    _run(command, "ffmpeg frame sampling")
    frame_size = width * height
    try:
        data = raw_path.read_bytes()
    except OSError as exc:
        raise PpsError(f"could not read sampled frames from {raw_path}: {exc}") from exc
    frames: list[FrameSignature] = []
    for index in range(0, len(data) // frame_size):
        offset = index * frame_size
        samples = data[offset : offset + frame_size]
        frames.append(
            FrameSignature(
                time_seconds=index / fps,
                width=width,
                height=height,
                samples=samples,
            )
        )
    return frames


def extract_stills_png(
    recording: Path,
    timestamps: list[float],
    output_dir: Path,
    work_dir: Path,
    env: Environment,
    *,
    fps: float = DEFAULT_SAMPLE_FPS,
) -> None:
    if not timestamps:
        return
    if not env.ffmpeg.found or env.ffmpeg.path is None:
        raise PpsError("ffmpeg is required to extract Still images")
    from podleparsesskewl.document import still_image_name

    with writing(f"the Still images in {output_dir}"):
        (output_dir / "stills").mkdir(parents=True, exist_ok=True)
        selection = "+".join(f"eq(n\\,{round(timestamp * fps)})" for timestamp in timestamps)
        filters = work_dir / "stills.filter"
        filters.write_text(f"{_sampling_filter(fps)},select={selection}", encoding="utf-8")
    command = [
        str(env.ffmpeg.path), "-v", "error", "-i", str(recording),
        "-filter_script:v", str(filters), "-fps_mode", "passthrough",
        "-frames:v", str(len(timestamps)), "-y",
        str(output_dir / "stills" / "still-%03d.png"),
    ]
    _run(command, "ffmpeg still extract")
    for index in range(1, len(timestamps) + 1):
        dest = output_dir / still_image_name(index)
        if not dest.is_file() or dest.stat().st_size == 0:
            raise PpsError(f"ffmpeg did not write a Still image at {dest}")


def _sampling_filter(fps: float) -> str:
    return f"fps={fps}:start_time=0:round=up"


def extract_audio_wav(
    recording: Path,
    dest: Path,
    env: Environment,
) -> Path:
    if not env.ffmpeg.found or env.ffmpeg.path is None:
        raise PpsError("ffmpeg is required to extract audio for transcription")
    with writing(f"the folder for {dest}"):
        dest.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(env.ffmpeg.path),
        "-v",
        "error",
        "-i",
        str(recording),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-y",
        str(dest),
    ]
    _run(command, "ffmpeg audio extract")
    if not dest.is_file():
        raise PpsError(f"ffmpeg did not write audio to {dest}")
    return dest


def _run(command: list[str], label: str) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise PpsError(f"{label} failed to start: {exc}") from exc
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise PpsError(f"{label} failed: {err or 'exit ' + str(result.returncode)}")
    return result
