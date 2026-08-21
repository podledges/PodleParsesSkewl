from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from podleparsesskewl.document import Cue, LectureDocument, Section, SourceInfo, Still, Transcript
from podleparsesskewl.pipeline import load_document, write_document
from podleparsesskewl.report import render_html, render_markdown, write_plain_views


def _document() -> LectureDocument:
    stills = (
        Still("still-001", 1, 0.0, 5.0, "stills/still-001.png"),
        Still("still-002", 2, 5.0, 10.0, "stills/still-002.png"),
    )
    cues = (
        Cue(1.0, 2.0, "Hello class."),
        Cue(6.0, 7.0, "Look at this graph."),
    )
    return LectureDocument(
        title="Sample Lecture",
        source=SourceInfo(
            recording="lecture.mp4",
            duration_seconds=10.0,
            transcript_source="sidecar:srt:lecture.srt",
            width=1920,
            height=1080,
        ),
        stills=stills,
        transcript=Transcript(cues=cues, source="sidecar:srt:lecture.srt"),
        sections=(
            Section("still-001", "Hello class.", (0,)),
            Section("still-002", "Look at this graph.", (1,)),
        ),
    )


def _assign(payload: dict, dotted: str, value: object) -> None:
    target = payload
    keys = dotted.split(".")
    for key in keys[:-1]:
        target = target[int(key)] if key.isdigit() else target[key]
    last = keys[-1]
    if last.isdigit():
        target[int(last)] = value
    else:
        target[last] = value


class ReportTests(unittest.TestCase):
    def test_html_pairs_each_still_with_a_separator_and_said_text(self) -> None:
        html = render_html(_document())
        self.assertIn("<h1>Sample Lecture</h1>", html)
        self.assertIn('src="stills/still-001.png"', html)
        self.assertIn("Hello class.", html)
        self.assertIn("Look at this graph.", html)
        self.assertGreaterEqual(html.count("<hr>"), 3)
        first_img = html.index("stills/still-001.png")
        first_hr_after = html.index("<hr>", first_img)
        first_said = html.index("Hello class.")
        self.assertLess(first_hr_after, first_said)

    def test_html_escapes_said_text(self) -> None:
        document = _document()
        evil = LectureDocument(
            title=document.title,
            source=document.source,
            stills=document.stills,
            transcript=document.transcript,
            sections=(
                Section("still-001", "<script>alert(1)</script>", (0,)),
                document.sections[1],
            ),
        )
        html = render_html(evil)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_markdown_uses_separators_between_still_and_transcript(self) -> None:
        markdown = render_markdown(_document())
        self.assertIn("![Still 1](stills/still-001.png)", markdown)
        self.assertIn("00:00:00 - 00:00:05", markdown)
        self.assertIn("---", markdown)
        self.assertIn("Hello class.", markdown)

    def test_said_follows_still_id_not_section_order(self) -> None:
        document = _document()
        reordered = LectureDocument(
            title=document.title,
            source=document.source,
            stills=document.stills,
            transcript=document.transcript,
            sections=(document.sections[1], document.sections[0]),
        )
        html = render_html(reordered)
        markdown = render_markdown(reordered)
        for view in (html, markdown):
            self.assertLess(view.index("Hello class."), view.index("Look at this graph."))

    def test_a_dropped_section_leaves_its_still_empty_instead_of_shifting(self) -> None:
        document = _document()
        trimmed = LectureDocument(
            title=document.title,
            source=document.source,
            stills=document.stills,
            transcript=document.transcript,
            sections=(document.sections[1],),
        )
        html = render_html(trimmed)
        first_still = html.index("stills/still-001.png")
        second_still = html.index("stills/still-002.png")
        said = html.index("Look at this graph.")
        self.assertGreater(said, second_still)
        self.assertNotIn("Hello class.", html)
        self.assertLess(first_still, second_still)

    def test_duplicate_still_ids_are_reported(self) -> None:
        from podleparsesskewl.report import pairing_problems

        document = _document()
        cloned = LectureDocument(
            title=document.title,
            source=document.source,
            stills=(
                document.stills[0],
                Still("still-001", 2, 5.0, 10.0, "stills/still-002.png"),
            ),
            transcript=document.transcript,
            sections=(document.sections[0],),
        )
        problems = pairing_problems(cloned)
        self.assertEqual(len(problems), 1)
        self.assertIn("still-001", problems[0])
        self.assertEqual(render_html(cloned).count("Hello class."), 2)

    def test_a_silent_still_keeps_one_separator_and_no_empty_said(self) -> None:
        document = _document()
        silent_first = LectureDocument(
            title=document.title,
            source=document.source,
            stills=document.stills,
            transcript=document.transcript,
            sections=(Section("still-001", "", ()), document.sections[1]),
        )
        html = render_html(silent_first)
        markdown = render_markdown(silent_first)

        self.assertNotIn('<div class="said"></div>', html)
        self.assertNotIn("<hr>\n<hr>", html)
        between = html.index("stills/still-001.png"), html.index("stills/still-002.png")
        self.assertEqual(html.count("<hr>", *between), 1)
        self.assertNotIn("---\n\n---", markdown)
        self.assertIn("---", markdown)
        self.assertIn("Look at this graph.", markdown)

    def test_invalid_document_payload_is_a_user_error(self) -> None:
        from podleparsesskewl.errors import PpsError

        with self.assertRaises(PpsError) as raised:
            LectureDocument.from_json_dict({"title": "x"})
        self.assertIn("source", str(raised.exception))

    def test_wrong_typed_fields_are_user_errors_not_renderer_crashes(self) -> None:
        from podleparsesskewl.errors import PpsError

        payload = _document().to_json_dict()
        broken = {
            "title": None,
            "stills.0.start_seconds": "half past",
            "stills.0.image": 5,
            "stills.0.index": "first",
            "sections.0.said": None,
            "source.duration_seconds": {},
            "transcript.cues.0.text": 7,
            "stills": "still-001",
            "transcript": [],
        }
        for field, value in broken.items():
            with self.subTest(field=field):
                candidate = json.loads(json.dumps(payload))
                _assign(candidate, field, value)
                with self.assertRaises(PpsError) as raised:
                    LectureDocument.from_json_dict(candidate)
                self.assertIn(field.split(".")[0], str(raised.exception))

    def test_non_finite_numbers_are_user_errors(self) -> None:
        from podleparsesskewl.errors import PpsError

        payload = _document().to_json_dict()
        broken = {
            "stills.0.start_seconds": "1e400",
            "stills.0.end_seconds": "inf",
            "source.duration_seconds": float("inf"),
            "transcript.cues.0.start_seconds": float("nan"),
            "stills.0.index": float("inf"),
            "source.width": 10**400,
        }
        for field, value in broken.items():
            with self.subTest(field=field):
                candidate = json.loads(json.dumps(_document().to_json_dict()))
                _assign(candidate, field, value)
                with self.assertRaises(PpsError):
                    LectureDocument.from_json_dict(candidate)
        self.assertEqual(payload["title"], "Sample Lecture")

    def test_fractional_count_fields_are_user_errors(self) -> None:
        from podleparsesskewl.errors import PpsError

        payload = _document().to_json_dict()
        for field in ("stills.0.index", "source.width", "sections.0.cue_indexes.0"):
            with self.subTest(field=field):
                candidate = json.loads(json.dumps(payload))
                _assign(candidate, field, 1.9)
                with self.assertRaises(PpsError):
                    LectureDocument.from_json_dict(candidate)

    def test_write_document_refuses_non_finite_numbers(self) -> None:
        from podleparsesskewl.errors import PpsError

        document = _document()
        broken = LectureDocument(
            title=document.title,
            source=document.source,
            stills=document.stills,
            transcript=Transcript(
                cues=(Cue(float("inf"), 2.0, "Hi"),), source=document.transcript.source
            ),
            sections=document.sections,
        )
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            with self.assertRaises(PpsError):
                write_document(broken, folder)
            self.assertFalse((folder / "lecture.json").exists())

    def test_written_documents_are_strict_json(self) -> None:
        def reject(_token: str) -> float:
            raise AssertionError("lecture.json must not carry Infinity/NaN tokens")

        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            path = write_document(_document(), folder)
            json.loads(path.read_text(encoding="utf-8"), parse_constant=reject)

    def test_orphaned_section_ids_are_reported(self) -> None:
        from podleparsesskewl.report import pairing_problems

        document = _document()
        self.assertEqual(pairing_problems(document), [])
        mistyped = LectureDocument(
            title=document.title,
            source=document.source,
            stills=document.stills,
            transcript=document.transcript,
            sections=(
                Section("still-01", "Hello class.", (0,)),
                document.sections[1],
            ),
        )
        problems = pairing_problems(mistyped)
        self.assertEqual(len(problems), 1)
        self.assertIn("still-01", problems[0])
        self.assertNotIn("Hello class.", render_html(mistyped))

    def test_duplicate_section_ids_keep_every_said_and_are_reported(self) -> None:
        from podleparsesskewl.report import pairing_problems

        document = _document()
        split = LectureDocument(
            title=document.title,
            source=document.source,
            stills=document.stills,
            transcript=document.transcript,
            sections=(
                Section("still-001", "AAA", (0,)),
                Section("still-001", "BBB", ()),
                document.sections[1],
            ),
        )
        html = render_html(split)
        markdown = render_markdown(split)
        for view in (html, markdown):
            self.assertIn("AAA", view)
            self.assertIn("BBB", view)
            self.assertLess(view.index("AAA"), view.index("BBB"))
        problems = pairing_problems(split)
        self.assertEqual(len(problems), 1)
        self.assertIn("still-001", problems[0])

    def test_html_head_declares_a_mobile_viewport(self) -> None:
        head = render_html(_document()).split("</head>")[0]
        self.assertIn('<meta name="viewport" content="width=device-width, initial-scale=1">', head)

    def test_numeric_strings_are_accepted_for_times(self) -> None:
        payload = _document().to_json_dict()
        payload["stills"][0]["start_seconds"] = "0"
        payload["source"]["duration_seconds"] = "10"
        document = LectureDocument.from_json_dict(payload)
        self.assertEqual(document.stills[0].start_seconds, 0.0)
        self.assertIn("00:00:10", render_html(document))

    def test_document_round_trip_json(self) -> None:
        document = _document()
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            path = write_document(document, folder)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "podleparsesskewl.lecture/v1")
            loaded = load_document(path)
            self.assertEqual(loaded.title, document.title)
            self.assertEqual(loaded.sections[1].said, "Look at this graph.")
            html_path, md_path = write_plain_views(loaded, folder)
            self.assertTrue(html_path.is_file())
            self.assertTrue(md_path.is_file())
