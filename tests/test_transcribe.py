from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from podleparsesskewl.errors import PpsError
from podleparsesskewl.transcribe import load_transcript

FIXTURES = Path(__file__).parent / "fixtures"


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
