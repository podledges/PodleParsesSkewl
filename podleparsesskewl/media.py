"""ffmpeg/ffprobe adapters for probing, sampling, and extracting Stills."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from podleparsesskewl.deps import Environment
from podleparsesskewl.errors import PpsError
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
        if kind == "video":
            has_video = True
            if stream.get("width"):
                width = int(stream["width"])
            if stream.get("height"):
                height = int(stream["height"])
            if duration == 0.0:
                duration = _optional_seconds(stream.get("duration")) or 0.0
        elif kind == "audio":
            has_audio = True
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
    except (TypeError, ValueError):
        return None
    if seconds != seconds or seconds < 0:  # NaN or negative
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
    work_dir.mkdir(parents=True, exist_ok=True)
    raw_path = work_dir / "signatures.gray"
    command = [
        str(env.ffmpeg.path),
        "-v",
        "error",
        "-i",
        str(recording),
        "-vf",
        f"fps={fps},scale={width}:{height}:flags=fast_bilinear,format=gray",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "-y",
        str(raw_path),
    ]
    _run(command, "ffmpeg frame sampling")
    frame_size = width * height
    data = raw_path.read_bytes()
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


def extract_still_png(
    recording: Path,
    timestamp_seconds: float,
    dest: Path,
    env: Environment,
) -> None:
    if not env.ffmpeg.found or env.ffmpeg.path is None:
        raise PpsError("ffmpeg is required to extract Still images")
    dest.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(env.ffmpeg.path),
        "-v",
        "error",
        "-ss",
        f"{max(0.0, timestamp_seconds):.3f}",
        "-i",
        str(recording),
        "-frames:v",
        "1",
        "-update",
        "1",
        "-y",
        str(dest),
    ]
    _run(command, "ffmpeg still extract")
    if not dest.is_file() or dest.stat().st_size == 0:
        raise PpsError(f"ffmpeg did not write a Still image at {dest}")


def extract_audio_wav(
    recording: Path,
    dest: Path,
    env: Environment,
) -> Path:
    if not env.ffmpeg.found or env.ffmpeg.path is None:
        raise PpsError("ffmpeg is required to extract audio for transcription")
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
