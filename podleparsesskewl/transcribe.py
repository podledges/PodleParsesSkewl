"""Obtain a Transcript from a sidecar or a local audio engine."""

from __future__ import annotations

import json
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from podleparsesskewl.captions import discover_sidecar, load_sidecar
from podleparsesskewl.deps import Environment
from podleparsesskewl.document import Cue, Transcript, cue_text, finite_seconds
from podleparsesskewl.errors import PpsError
from podleparsesskewl.media import extract_audio_wav


def load_transcript(
    recording: Path,
    env: Environment,
    *,
    sidecar: Path | None = None,
    work_dir: Path | None = None,
    has_audio: bool | None = None,
) -> Transcript:
    """Prefer an explicit or adjacent sidecar; otherwise transcribe locally."""
    chosen = sidecar if sidecar is not None else discover_sidecar(recording)
    if chosen is not None:
        if not chosen.is_file():
            raise PpsError(f"transcript sidecar not found: {chosen}")
        return load_sidecar(chosen)
    if has_audio is False:
        raise PpsError(
            f"this Recording has no audio track: {recording}. There is nothing to "
            "transcribe, so supply a .srt, .vtt, or .json caption sidecar next to it "
            "or with --transcript."
        )
    if not env.can_transcribe_audio:
        raise PpsError(
            "no caption sidecar found and no local transcription engine is available. "
            "Place a .srt, .vtt, or .json file next to the Recording, or install "
            "faster-whisper."
        )
    if work_dir is None:
        raise PpsError("work directory is required to transcribe audio")
    wav = extract_audio_wav(recording, work_dir / "audio.wav", env)
    return transcribe_wav(wav, env)


def transcribe_wav(wav: Path, env: Environment) -> Transcript:
    """Run the first available local engine against a WAV file."""
    try:
        import faster_whisper
    except ImportError:
        faster_whisper = None
    if faster_whisper is not None:
        return _faster_whisper(wav, faster_whisper)

    try:
        import whisper
    except ImportError:
        whisper = None
    if whisper is not None:
        return _openai_whisper(wav, whisper)

    for binary in ("whisper-ctranslate2", "whisper"):
        path = shutil.which(binary)
        if path:
            return _whisper_cli(wav, path, binary)

    raise PpsError(
        "a transcription engine was reported available but could not be used. "
        "Install faster-whisper, or supply a caption sidecar."
    )


@contextmanager
def _engine_failures(name: str) -> Iterator[None]:
    """Surface anything a third-party engine raises as a user-facing error."""
    try:
        yield
    except PpsError:
        raise
    except Exception as exc:
        raise PpsError(
            f"local transcription with {name} failed: {type(exc).__name__}: {exc}. "
            "Supply a caption sidecar, or check the engine and its model files."
        ) from exc


def _faster_whisper(wav: Path, module) -> Transcript:
    model_name = "base"
    name = f"faster-whisper:{model_name}"
    cues = []
    with _engine_failures(name):
        model = module.WhisperModel(model_name, device="cpu", compute_type="int8")
        segments, _info = model.transcribe(str(wav), vad_filter=True)
        for position, segment in enumerate(segments):
            text = cue_text(segment.text, f"{name} segment {position} text")
            if text:
                cues.append(
                    Cue(
                        start_seconds=_seconds(segment.start, name),
                        end_seconds=_seconds(segment.end, name),
                        text=text,
                    )
                )
    return Transcript(cues=tuple(cues), source=f"audio:faster-whisper:{model_name}")


def _openai_whisper(wav: Path, module) -> Transcript:
    model_name = "base"
    name = f"whisper:{model_name}"
    cues = []
    with _engine_failures(name):
        model = module.load_model(model_name)
        result = model.transcribe(str(wav), fp16=False)
        for position, segment in enumerate(result.get("segments") or []):
            text = cue_text(segment.get("text", ""), f"{name} segment {position} text")
            if text:
                cues.append(
                    Cue(
                        start_seconds=_seconds(segment.get("start", 0.0), name),
                        end_seconds=_seconds(segment.get("end", 0.0), name),
                        text=text,
                    )
                )
    return Transcript(cues=tuple(cues), source=f"audio:whisper:{model_name}")


def _seconds(value: object, engine: str) -> float:
    try:
        return finite_seconds(value, f"{engine} cue time")
    except PpsError as exc:
        raise PpsError(f"{engine} returned an unusable cue time {value!r}: {exc}") from exc


def _whisper_cli(wav: Path, binary: str, name: str) -> Transcript:
    command = [
        binary,
        str(wav),
        "--model",
        "base",
        "--output_format",
        "json",
        "--output_dir",
        str(wav.parent),
    ]
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        raise PpsError(f"{name} failed to start: {exc}") from exc
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise PpsError(f"{name} failed: {err or 'exit ' + str(result.returncode)}")
    json_path = wav.with_suffix(".json")
    if not json_path.is_file():
        raise PpsError(f"{name} did not write {json_path}")
    cues = []
    with _engine_failures(name):
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise PpsError(f"{name} wrote an unexpected JSON shape to {json_path}")
        for position, segment in enumerate(payload.get("segments") or []):
            text = cue_text(segment.get("text", ""), f"{name} segment {position} text")
            if text:
                cues.append(
                    Cue(
                        start_seconds=_seconds(segment.get("start", 0.0), name),
                        end_seconds=_seconds(segment.get("end", 0.0), name),
                        text=text,
                    )
                )
    return Transcript(cues=tuple(cues), source=f"audio:{name}:base")
