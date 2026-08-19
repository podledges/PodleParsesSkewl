from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from podleparsesskewl.captions import discover_sidecar, load_sidecar, parse_srt, parse_vtt
from podleparsesskewl.errors import PpsError

FIXTURES = Path(__file__).parent / "fixtures"


class CaptionTests(unittest.TestCase):
    def test_parse_srt_fixture(self) -> None:
        cues = parse_srt((FIXTURES / "sample.srt").read_text(encoding="utf-8"))
        self.assertEqual(len(cues), 3)
        self.assertEqual(cues[0].text, "Welcome to the first slide.")
        self.assertEqual(cues[0].start_seconds, 0.0)
        self.assertEqual(cues[0].end_seconds, 2.5)
        self.assertEqual(cues[1].start_seconds, 3.0)

    def test_parse_vtt_strips_tags(self) -> None:
        cues = parse_vtt((FIXTURES / "sample.vtt").read_text(encoding="utf-8"))
        self.assertEqual(len(cues), 3)
        self.assertEqual(cues[1].text, "Now we are looking at the second slide.")

    def test_load_json_sidecar(self) -> None:
        transcript = load_sidecar(FIXTURES / "sample.json")
        self.assertEqual(transcript.source, "sidecar:json:sample.json")
        self.assertEqual(len(transcript.cues), 3)
        self.assertEqual(transcript.cues[2].text, "A closing thought.")

    def test_discover_sidecar_prefers_srt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            recording = folder / "lecture.mp4"
            recording.write_bytes(b"")
            sidecar = folder / "lecture.srt"
            sidecar.write_text((FIXTURES / "sample.srt").read_text(encoding="utf-8"))
            found = discover_sidecar(recording)
            self.assertEqual(found, sidecar)

    def test_load_sidecar_rejects_unknown_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "notes.txt"
            path.write_text("hello")
            with self.assertRaises(PpsError):
                load_sidecar(path)

    def test_srt_without_index_numbers(self) -> None:
        text = "00:00:01,000 --> 00:00:02,000\nHello\n"
        cues = parse_srt(text)
        self.assertEqual(cues[0].text, "Hello")
        self.assertEqual(cues[0].start_seconds, 1.0)
