"""Obtain a Transcript from a sidecar or a local audio engine."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from podleparsesskewl.captions import discover_sidecar, load_sidecar
from podleparsesskewl.deps import Environment
from podleparsesskewl.document import Cue, Transcript
from podleparsesskewl.errors import PpsError
from podleparsesskewl.media import extract_audio_wav


def load_transcript(
    recording: Path,
    env: Environment,
    *,
    sidecar: Path | None = None,
    work_dir: Path | None = None,
) -> Transcript:
    """Prefer an explicit or adjacent sidecar; otherwise transcribe locally."""
    chosen = sidecar if sidecar is not None else discover_sidecar(recording)
    if chosen is not None:
        if not chosen.is_file():
            raise PpsError(f"transcript sidecar not found: {chosen}")
        return load_sidecar(chosen)
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


def _faster_whisper(wav: Path, module) -> Transcript:
    model_name = "base"
    model = module.WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(wav), vad_filter=True)
    cues = []
    for segment in segments:
        text = (segment.text or "").strip()
        if text:
            cues.append(
                Cue(
                    start_seconds=float(segment.start),
                    end_seconds=float(segment.end),
                    text=text,
                )
            )
    return Transcript(cues=tuple(cues), source=f"audio:faster-whisper:{model_name}")


def _openai_whisper(wav: Path, module) -> Transcript:
    model_name = "base"
    model = module.load_model(model_name)
    result = model.transcribe(str(wav), fp16=False)
    cues = []
    for segment in result.get("segments") or []:
        text = str(segment.get("text", "")).strip()
        if text:
            cues.append(
                Cue(
                    start_seconds=float(segment.get("start", 0.0)),
                    end_seconds=float(segment.get("end", 0.0)),
                    text=text,
                )
            )
    return Transcript(cues=tuple(cues), source=f"audio:whisper:{model_name}")


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
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    cues = []
    for segment in payload.get("segments") or []:
        text = str(segment.get("text", "")).strip()
        if text:
            cues.append(
                Cue(
                    start_seconds=float(segment.get("start", 0.0)),
                    end_seconds=float(segment.get("end", 0.0)),
                    text=text,
                )
            )
    return Transcript(cues=tuple(cues), source=f"audio:{name}:base")
