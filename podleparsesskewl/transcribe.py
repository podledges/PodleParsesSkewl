"""Obtain a Transcript from a sidecar or a local audio engine."""

from __future__ import annotations

import json
import shutil
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from podleparsesskewl.captions import discover_sidecar, load_sidecar
from podleparsesskewl.deps import Environment
from podleparsesskewl.document import Cue, Transcript, cue_text, finite_seconds
from podleparsesskewl.errors import PpsError
from podleparsesskewl.media import extract_audio_wav

DEFAULT_WHISPER_MODEL = "base"
DEFAULT_LOCAL_FILES_ROOT = Path("localdata")


@dataclass(frozen=True)
class TranscriptionOptions:
    model: str = DEFAULT_WHISPER_MODEL
    model_path: Path | None = None
    local_files_root: Path = DEFAULT_LOCAL_FILES_ROOT
    offline: bool = False

    @property
    def model_reference(self) -> str:
        return str(self.model_path) if self.model_path is not None else self.model



def load_transcript(
    recording: Path,
    env: Environment,
    *,
    sidecar: Path | None = None,
    work_dir: Path | None = None,
    has_audio: bool | None = None,
    transcription: TranscriptionOptions | None = None,
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
    return transcribe_wav(wav, env, transcription=transcription)


def transcribe_wav(
    wav: Path,
    env: Environment,
    *,
    transcription: TranscriptionOptions | None = None,
) -> Transcript:
    """Run the first available local engine, insisting on some speech."""
    transcript = _run_engine(wav, transcription or TranscriptionOptions())
    if not transcript.cues:
        raise PpsError(
            f"local transcription ({transcript.source}) found no speech in the Recording. "
            "The audio may be silent, too quiet, or in a form the engine filtered out. "
            "Supply a .srt, .vtt, or .json caption sidecar to review this Lecture."
        )
    return transcript


def _run_engine(wav: Path, options: TranscriptionOptions) -> Transcript:
    try:
        import faster_whisper
    except ImportError:
        faster_whisper = None
    if faster_whisper is not None:
        return _faster_whisper(wav, faster_whisper, options)

    try:
        import whisper
    except ImportError:
        whisper = None
    if whisper is not None:
        return _openai_whisper(wav, whisper, options)

    for binary in ("whisper-ctranslate2", "whisper"):
        path = shutil.which(binary)
        if path:
            return _whisper_cli(wav, path, binary, options)
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


def _faster_whisper(wav: Path, module, options: TranscriptionOptions) -> Transcript:
    model_ref = options.model_reference
    name = f"faster-whisper:{model_ref}"
    cues = []
    with _engine_failures(name):
        if options.model_path is None:
            options.local_files_root.mkdir(parents=True, exist_ok=True)
        model = module.WhisperModel(
            model_ref,
            device="cpu",
            compute_type="int8",
            download_root=str(options.local_files_root),
            local_files_only=options.offline,
        )
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
    return Transcript(cues=tuple(cues), source=f"audio:faster-whisper:{model_ref}")


def _openai_whisper(wav: Path, module, options: TranscriptionOptions) -> Transcript:
    model_ref = options.model_reference
    name = f"whisper:{model_ref}"
    cues = []
    with _engine_failures(name):
        if options.model_path is None:
            if options.offline and not _openai_cached_model_exists(module, options):
                raise PpsError(
                    f"openai-whisper model {options.model!r} is not present under "
                    f"{options.local_files_root}; run once online to cache it or pass "
                    "--whisper-model-path."
                )
            options.local_files_root.mkdir(parents=True, exist_ok=True)
            model = module.load_model(options.model, download_root=str(options.local_files_root))
        else:
            model = module.load_model(str(options.model_path))
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
    return Transcript(cues=tuple(cues), source=f"audio:whisper:{model_ref}")


def _seconds(value: object, engine: str) -> float:
    try:
        return finite_seconds(value, f"{engine} cue time")
    except PpsError as exc:
        raise PpsError(f"{engine} returned an unusable cue time {value!r}: {exc}") from exc


def _openai_cached_model_exists(module, options: TranscriptionOptions) -> bool:
    candidate = options.local_files_root / f"{options.model}.pt"
    if candidate.is_file():
        return True
    models = getattr(module, "_MODELS", {})
    url = models.get(options.model) if isinstance(models, dict) else None
    if isinstance(url, str):
        return (options.local_files_root / url.rsplit("/", 1)[-1]).is_file()
    return False


def _whisper_cli(wav: Path, binary: str, name: str, options: TranscriptionOptions) -> Transcript:
    model_ref = options.model_reference
    if options.offline and options.model_path is None and not (options.local_files_root / f"{options.model}.pt").exists():
        raise PpsError(
            f"{name} cache-only transcription needs model {options.model!r} under "
            f"{options.local_files_root}, or pass --whisper-model-path."
        )
    if options.model_path is None:
        options.local_files_root.mkdir(parents=True, exist_ok=True)
    command = [
        binary,
        str(wav),
        "--model",
        model_ref,
        "--output_format",
        "json",
        "--output_dir",
        str(wav.parent),
    ]
    if name == "whisper" and options.model_path is None:
        command.extend(["--model_dir", str(options.local_files_root)])
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
    return Transcript(cues=tuple(cues), source=f"audio:{name}:{model_ref}")
