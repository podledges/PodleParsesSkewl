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
