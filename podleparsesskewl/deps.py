"""Graceful checks for ffmpeg, ffprobe, and local transcription engines."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from podleparsesskewl.config import running_under_wsl, windows_path_to_wsl

ENV_FFMPEG = "PODLEPARSESSKEWL_FFMPEG"
ENV_FFPROBE = "PODLEPARSESSKEWL_FFPROBE"


@dataclass(frozen=True)
class ToolStatus:
    name: str
    found: bool
    path: Path | None
    detail: str


@dataclass(frozen=True)
class Environment:
    ffmpeg: ToolStatus
    ffprobe: ToolStatus
    transcriber: ToolStatus

    @property
    def can_parse_video(self) -> bool:
        return self.ffmpeg.found and self.ffprobe.found

    @property
    def can_transcribe_audio(self) -> bool:
        return self.transcriber.found


def inspect_environment() -> Environment:
    ffmpeg = _ffmpeg_status()
    ffprobe = _ffprobe_status(ffmpeg.path)
    transcriber = _transcriber_status()
    return Environment(ffmpeg=ffmpeg, ffprobe=ffprobe, transcriber=transcriber)


def format_doctor(env: Environment) -> str:
    lines = ["PodleParsesSkewl doctor", ""]
    for tool in (env.ffmpeg, env.ffprobe, env.transcriber):
        mark = "ok" if tool.found else "missing"
        location = str(tool.path) if tool.path is not None else "-"
        lines.append(f"  {tool.name:<12} {mark:<8} {location}")
        if tool.detail:
            lines.append(f"               {tool.detail}")
    lines.append("")
    if env.can_parse_video:
        lines.append("Video parsing: ready (ffmpeg + ffprobe).")
    else:
        lines.append("Video parsing: install ffmpeg (includes ffprobe) and retry.")
    if env.can_transcribe_audio:
        lines.append("Audio transcription: ready. Sidecar captions still take priority.")
    else:
        lines.append(
            "Audio transcription: no local engine. A sidecar .srt/.vtt/.json still works."
        )
    return "\n".join(lines)


def _ffmpeg_status() -> ToolStatus:
    path, problem = _resolve_binary("ffmpeg", ENV_FFMPEG)
    if path is None:
        return ToolStatus(
            name="ffmpeg",
            found=False,
            path=None,
            detail=problem or "required to read MP4 recordings and extract Stills",
        )
    version = _run_version([str(path), "-version"])
    return ToolStatus(name="ffmpeg", found=True, path=path, detail=version)


def _ffprobe_status(ffmpeg_path: Path | None) -> ToolStatus:
    path, problem = _resolve_binary("ffprobe", ENV_FFPROBE)
    if path is None and ffmpeg_path is not None:
        for sibling in _ffprobe_siblings(ffmpeg_path):
            if sibling.is_file():
                path = sibling
                problem = ""
                break
    if path is None:
        return ToolStatus(
            name="ffprobe",
            found=False,
            path=None,
            detail=problem or "usually installed with ffmpeg; used to read duration and size",
        )
    version = _run_version([str(path), "-version"])
    return ToolStatus(name="ffprobe", found=True, path=path, detail=version)


def _ffprobe_siblings(ffmpeg_path: Path) -> list[Path]:
    """Candidate ffprobe paths next to ffmpeg, keeping its own suffix (.exe)."""
    names = ["ffprobe" + ffmpeg_path.suffix, "ffprobe"]
    seen: list[Path] = []
    for name in names:
        candidate = ffmpeg_path.with_name(name)
        if candidate not in seen:
            seen.append(candidate)
    return seen


def _transcriber_status() -> ToolStatus:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        pass
    else:
        return ToolStatus(
            name="transcriber",
            found=True,
            path=None,
            detail="faster-whisper (Python)",
        )
    try:
        import whisper  # noqa: F401
    except ImportError:
        pass
    else:
        return ToolStatus(
            name="transcriber",
            found=True,
            path=None,
            detail="openai-whisper (Python)",
        )
    whisper_cli = shutil.which("whisper")
    if whisper_cli:
        return ToolStatus(
            name="transcriber",
            found=True,
            path=Path(whisper_cli),
            detail="CLI whisper",
        )
    ctranslate2_cli = shutil.which("whisper-ctranslate2")
    if ctranslate2_cli:
        return ToolStatus(
            name="transcriber",
            found=False,
            path=Path(ctranslate2_cli),
            detail="whisper-ctranslate2 needs --whisper-model-path and cannot be auto-used by doctor",
        )
    return ToolStatus(
        name="transcriber",
        found=False,
        path=None,
        detail="optional when a caption sidecar is present; install faster-whisper otherwise",
    )


def _resolve_binary(name: str, env_key: str) -> tuple[Path | None, str]:
    """Resolve a tool path; an override that cannot be used explains itself."""
    override = os.environ.get(env_key)
    if override:
        for candidate in _override_candidates(override):
            if candidate.is_file():
                return candidate, ""
        return None, (
            f"${env_key} is set but is not a file: {override}. "
            f"Point it at the {name} binary, or unset it to use PATH."
        )
    found = shutil.which(name)
    return (Path(found) if found else None), ""


def _override_candidates(override: str) -> list[Path]:
    candidates = [Path(override)]
    if running_under_wsl():
        translated = windows_path_to_wsl(override)
        if translated is not None:
            candidates.append(Path(translated))
    return candidates


def _run_version(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "found, version unknown"
    first = (result.stdout or result.stderr).splitlines()[:1]
    return first[0].strip() if first else "found"
