from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from podleparsesskewl.captions import discover_sidecar, load_sidecar, parse_srt, parse_vtt
from podleparsesskewl.errors import PpsError

FIXTURES = Path(__file__).parent / "fixtures"


def _document_json() -> str:
    import json

    from podleparsesskewl.document import (
        Cue,
        LectureDocument,
        Section,
        SourceInfo,
        Still,
        Transcript,
    )

    document = LectureDocument(
        title="Lecture",
        source=SourceInfo("lecture.mp4", 4.0, "sidecar:srt:lecture.srt"),
        stills=(Still("still-001", 1, 0.0, 4.0, "stills/still-001.png"),),
        transcript=Transcript((Cue(1.0, 2.0, "Said here."),), "sidecar:srt:lecture.srt"),
        sections=(Section("still-001", "Said here.", (0,)),),
    )
    return json.dumps(document.to_json_dict(), indent=2)


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

    def test_loose_srt_timestamps_are_a_user_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "lecture.srt"
            path.write_text("1\n0:0:1 --> 0:0:2\nHello\n", encoding="utf-8")
            with self.assertRaises(PpsError) as raised:
                load_sidecar(path)
        self.assertIn("0:0:1", str(raised.exception))

    def test_non_utf8_sidecar_is_a_user_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "lecture.srt"
            path.write_bytes("1\n00:00:01,000 --> 00:00:02,000\nCaf\xe9\n".encode("cp1252"))
            with self.assertRaises(PpsError) as raised:
                load_sidecar(path)
        self.assertIn("UTF-8", str(raised.exception))

    def test_malformed_json_sidecar_is_a_user_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "lecture.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(PpsError):
                load_sidecar(path)

    def test_non_numeric_json_cue_time_is_a_user_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "lecture.json"
            path.write_text(
                '[{"start": "soon", "end": 2.0, "text": "Hello"}]', encoding="utf-8"
            )
            with self.assertRaises(PpsError) as raised:
                load_sidecar(path)
        self.assertIn("start", str(raised.exception))

    def test_non_finite_json_cue_times_are_rejected(self) -> None:
        for body in (
            '[{"start": 1e400, "end": 2.0, "text": "Hi"}]',
            '[{"start": 0.0, "end": Infinity, "text": "Hi"}]',
            '[{"start": NaN, "end": 2.0, "text": "Hi"}]',
        ):
            with self.subTest(body=body):
                with tempfile.TemporaryDirectory() as raw:
                    path = Path(raw) / "lecture.json"
                    path.write_text(body, encoding="utf-8")
                    with self.assertRaises(PpsError) as raised:
                        load_sidecar(path)
                self.assertIn("finite", str(raised.exception))

    def test_a_null_text_cue_is_skipped_like_an_absent_one(self) -> None:
        body = (
            '[{"start": 1, "end": 2, "text": "Only this was said."},'
            ' {"start": 3, "end": 4, "text": null},'
            ' {"start": 5, "end": 6},'
            ' {"start": 7, "end": 8, "text": "  "}]'
        )
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "lecture.json"
            path.write_text(body, encoding="utf-8")
            transcript = load_sidecar(path)
        self.assertEqual([cue.text for cue in transcript.cues], ["Only this was said."])

    def test_a_sidecar_of_only_null_text_cues_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "lecture.json"
            path.write_text('[{"start": 1, "end": 2, "text": null}]', encoding="utf-8")
            with self.assertRaises(PpsError) as raised:
                load_sidecar(path)
        self.assertIn("empty or invalid", str(raised.exception).lower())

    def test_non_string_cue_text_is_never_turned_into_said(self) -> None:
        for body in (
            '[{"start": 1, "end": 2, "text": 123}]',
            '[{"start": 1, "end": 2, "text": {"a": 1}}]',
            '[{"start": 1, "end": 2, "text": ["a"]}]',
        ):
            with self.subTest(body=body):
                with tempfile.TemporaryDirectory() as raw:
                    path = Path(raw) / "lecture.json"
                    path.write_text(body, encoding="utf-8")
                    with self.assertRaises(PpsError) as raised:
                        load_sidecar(path)
                self.assertIn("must be text", str(raised.exception))

    def test_bool_cue_times_are_rejected_like_the_document_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "lecture.json"
            path.write_text('[{"start": true, "end": 2, "text": "a"}]', encoding="utf-8")
            with self.assertRaises(PpsError) as raised:
                load_sidecar(path)
        self.assertIn("bool", str(raised.exception))

    def test_missing_sidecar_file_is_a_user_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(PpsError):
                load_sidecar(Path(raw) / "absent.srt")

    def test_unrecognized_json_shape_is_rejected_not_silently_empty(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "lecture.json"
            path.write_text('{"transcription": [{"t": 1}]}', encoding="utf-8")
            with self.assertRaises(PpsError) as raised:
                load_sidecar(path)
        message = str(raised.exception)
        self.assertIn("cues", message)
        self.assertIn("segments", message)

    def test_empty_srt_stub_stops_the_run_with_a_recovery_hint(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "lecture.srt"
            path.write_text("", encoding="utf-8")
            with self.assertRaises(PpsError) as raised:
                load_sidecar(path)
        message = str(raised.exception).lower()
        self.assertIn("empty or invalid", message)
        self.assertIn("remove it", message)

    def test_header_only_vtt_stub_stops_the_run(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "lecture.vtt"
            path.write_text("WEBVTT\n\n", encoding="utf-8")
            with self.assertRaises(PpsError) as raised:
                load_sidecar(path)
        self.assertIn("empty or invalid", str(raised.exception).lower())

    def test_json_sidecar_without_any_cue_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "lecture.json"
            path.write_text('{"cues": []}', encoding="utf-8")
            with self.assertRaises(PpsError):
                load_sidecar(path)

    def test_lecture_document_is_not_accepted_as_a_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "lecture.json"
            path.write_text(_document_json(), encoding="utf-8")
            with self.assertRaises(PpsError) as raised:
                load_sidecar(path)
        self.assertIn("Lecture Document", str(raised.exception))

    def test_discover_sidecar_skips_a_lecture_document(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            recording = folder / "lecture.mp4"
            recording.write_bytes(b"")
            (folder / "lecture.json").write_text(_document_json(), encoding="utf-8")
            self.assertIsNone(discover_sidecar(recording))

    def test_discover_sidecar_still_finds_a_real_json_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            recording = folder / "lecture.mp4"
            recording.write_bytes(b"")
            sidecar = folder / "lecture.json"
            sidecar.write_text(
                (FIXTURES / "sample.json").read_text(encoding="utf-8"), encoding="utf-8"
            )
            self.assertEqual(discover_sidecar(recording), sidecar)

    def test_srt_without_index_numbers(self) -> None:
        text = "00:00:01,000 --> 00:00:02,000\nHello\n"
        cues = parse_srt(text)
        self.assertEqual(cues[0].text, "Hello")
        self.assertEqual(cues[0].start_seconds, 1.0)
