from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import Mock

from podleparsesskewl.errors import PpsError
from podleparsesskewl.transcribe import load_transcript, transcribe_wav

FIXTURES = Path(__file__).parent / "fixtures"


def _faster_whisper_module(model) -> types.ModuleType:
    module = types.ModuleType("faster_whisper")
    module.WhisperModel = Mock(return_value=model)
    return module


class TranscribeTests(unittest.TestCase):
    def test_sidecar_is_used_without_an_audio_engine(self) -> None:
        env = Mock()
        env.can_transcribe_audio = False
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            recording = folder / "lecture.mp4"
            recording.write_bytes(b"")
            sidecar = folder / "lecture.srt"
            sidecar.write_text((FIXTURES / "sample.srt").read_text(encoding="utf-8"))
            transcript = load_transcript(recording, env)
        self.assertTrue(transcript.source.startswith("sidecar:srt"))
        self.assertEqual(transcript.cues[0].text, "Welcome to the first slide.")

    def test_missing_sidecar_and_engine_is_a_clear_error(self) -> None:
        env = Mock()
        env.can_transcribe_audio = False
        with tempfile.TemporaryDirectory() as raw:
            recording = Path(raw) / "lecture.mp4"
            recording.write_bytes(b"")
            with self.assertRaises(PpsError) as raised:
                load_transcript(recording, env)
        message = str(raised.exception).lower()
        self.assertIn("sidecar", message)
        self.assertIn("faster-whisper", message)

    def test_recording_without_audio_and_without_sidecar_says_so(self) -> None:
        env = Mock()
        env.can_transcribe_audio = True
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            recording = folder / "lecture.mp4"
            recording.write_bytes(b"")
            with self.assertRaises(PpsError) as raised:
                load_transcript(recording, env, work_dir=folder, has_audio=False)
        message = str(raised.exception).lower()
        self.assertIn("no audio track", message)
        self.assertIn("sidecar", message)

    def test_a_failing_audio_engine_is_a_user_error(self) -> None:
        module = types.ModuleType("faster_whisper")
        module.WhisperModel = Mock(side_effect=RuntimeError("could not download model"))
        with tempfile.TemporaryDirectory() as raw:
            wav = Path(raw) / "audio.wav"
            wav.write_bytes(b"")
            with mock.patch.dict(sys.modules, {"faster_whisper": module}):
                with self.assertRaises(PpsError) as raised:
                    transcribe_wav(wav, Mock())
        message = str(raised.exception)
        self.assertIn("faster-whisper", message)
        self.assertIn("could not download model", message)

    def test_a_non_numeric_engine_cue_time_is_a_user_error(self) -> None:
        segment = types.SimpleNamespace(start="soon", end=2.0, text="Hello")
        model = Mock()
        model.transcribe.return_value = ([segment], None)
        with tempfile.TemporaryDirectory() as raw:
            wav = Path(raw) / "audio.wav"
            wav.write_bytes(b"")
            with mock.patch.dict(sys.modules, {"faster_whisper": _faster_whisper_module(model)}):
                with self.assertRaises(PpsError) as raised:
                    transcribe_wav(wav, Mock())
        self.assertIn("'soon'", str(raised.exception))

    def test_a_non_string_engine_segment_is_a_user_error(self) -> None:
        segment = types.SimpleNamespace(start=1.0, end=2.0, text={"word": "Hello"})
        model = Mock()
        model.transcribe.return_value = ([segment], None)
        with tempfile.TemporaryDirectory() as raw:
            wav = Path(raw) / "audio.wav"
            wav.write_bytes(b"")
            with mock.patch.dict(sys.modules, {"faster_whisper": _faster_whisper_module(model)}):
                with self.assertRaises(PpsError) as raised:
                    transcribe_wav(wav, Mock())
        self.assertIn("must be text", str(raised.exception))

    def test_a_none_text_segment_does_not_abort_the_transcription(self) -> None:
        segments = [
            types.SimpleNamespace(start=1.0, end=2.0, text="Hello class."),
            types.SimpleNamespace(start=3.0, end=4.0, text=None),
        ]
        model = Mock()
        model.transcribe.return_value = (segments, None)
        with tempfile.TemporaryDirectory() as raw:
            wav = Path(raw) / "audio.wav"
            wav.write_bytes(b"")
            with mock.patch.dict(sys.modules, {"faster_whisper": _faster_whisper_module(model)}):
                transcript = transcribe_wav(wav, Mock())
        self.assertEqual([cue.text for cue in transcript.cues], ["Hello class."])

    def test_engine_cues_become_a_transcript(self) -> None:
        segment = types.SimpleNamespace(start=1.0, end=2.0, text=" Hello class. ")
        model = Mock()
        model.transcribe.return_value = ([segment], None)
        with tempfile.TemporaryDirectory() as raw:
            wav = Path(raw) / "audio.wav"
            wav.write_bytes(b"")
            with mock.patch.dict(sys.modules, {"faster_whisper": _faster_whisper_module(model)}):
                transcript = transcribe_wav(wav, Mock())
        self.assertEqual(transcript.source, "audio:faster-whisper:base")
        self.assertEqual(transcript.cues[0].text, "Hello class.")
        self.assertEqual(transcript.cues[0].start_seconds, 1.0)

    def test_explicit_sidecar_path(self) -> None:
        env = Mock()
        env.can_transcribe_audio = False
        with tempfile.TemporaryDirectory() as raw:
            recording = Path(raw) / "lecture.mp4"
            recording.write_bytes(b"")
            transcript = load_transcript(
                recording,
                env,
                sidecar=FIXTURES / "sample.vtt",
            )
        self.assertTrue(transcript.source.startswith("sidecar:vtt"))
        self.assertEqual(len(transcript.cues), 3)
