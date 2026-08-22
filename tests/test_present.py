from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from podleparsesskewl.cli import main
from podleparsesskewl.document import Cue, LectureDocument, Section, SourceInfo, Still, Transcript
from podleparsesskewl.pipeline import write_document
from podleparsesskewl.present import PRESENT_NAME, render_present, write_present


def _document() -> LectureDocument:
    stills = (
        Still("still-001", 1, 0.0, 5.0, "stills/still-001.png"),
        Still("still-002", 2, 5.0, 12.0, "stills/still-002.png"),
        Still("still-003", 3, 12.0, 20.0, "stills/still-003.png"),
    )
    cues = (
        Cue(1.0, 3.0, "A hash table maps keys to values in expected constant time."),
        Cue(6.0, 9.0, "For example, you can use a hash table to count words in a document."),
        Cue(13.0, 15.0, ""),
    )
    return LectureDocument(
        title="Hash tables",
        source=SourceInfo(
            recording="lecture.mp4",
            duration_seconds=20.0,
            transcript_source="sidecar:srt:lecture.srt",
            width=1920,
            height=1080,
        ),
        stills=stills,
        transcript=Transcript(cues=cues, source="sidecar:srt:lecture.srt"),
        sections=(
            Section("still-001", "A hash table maps keys to values in expected constant time.", (0,)),
            Section(
                "still-002",
                "For example, you can use a hash table to count words in a document.",
                (1,),
            ),
            Section("still-003", "", ()),
        ),
    )


class PresentReportTests(unittest.TestCase):
    def test_present_html_grounds_topics_in_said_and_shown(self) -> None:
        report = render_present(_document())
        self.assertIn("<!DOCTYPE html>", report)
        self.assertIn("Hash tables", report)
        self.assertIn("stills/still-001.png", report)
        self.assertIn("stills/still-002.png", report)
        self.assertIn("stills/still-003.png", report)
        self.assertIn("Executive summary", report)
        self.assertIn("Key concepts", report)
        self.assertIn("Timeline tied to Shown", report)
        self.assertIn("Review prompts", report)
        self.assertIn("In a nutshell", report)
        self.assertIn("Mental model", report)
        self.assertIn("How it actually works", report)
        self.assertIn("Where you would use this", report)
        self.assertIn("count words in a document", report)
        self.assertIn("still-001", report)
        self.assertIn("#f6f1e8", report)

    def test_silent_still_is_grouped_and_does_not_invent_speech(self) -> None:
        report = render_present(_document())
        self.assertIn("still-003", report)
        self.assertNotIn("No spoken explanation was paired with this Shown.", report)
        self.assertNotIn("comprehensive study guide", report.lower())
        self.assertNotIn("[[", report)
        self.assertNotIn("mermaid.js", report)
        self.assertNotIn("cdn.", report.lower())

    def test_applications_are_omitted_when_the_lecture_did_not_give_any(self) -> None:
        document = _document()
        no_app = LectureDocument(
            title=document.title,
            source=document.source,
            stills=(document.stills[0],),
            transcript=Transcript((document.transcript.cues[0],), document.transcript.source),
            sections=(document.sections[0],),
        )
        report = render_present(no_app)
        self.assertNotIn("Where you would use this", report)
        self.assertIn("hash table maps keys", report.lower())

    def test_present_escapes_said_text(self) -> None:
        document = _document()
        evil = LectureDocument(
            title=document.title,
            source=document.source,
            stills=(document.stills[0],),
            transcript=document.transcript,
            sections=(Section("still-001", "<script>alert(1)</script>", (0,)),),
        )
        report = render_present(evil)
        self.assertNotIn("<script>alert(1)</script>", report)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", report)

    def test_present_cli_writes_lecture_present_html(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            path = write_document(_document(), folder)
            code = main(["present", str(path)])
            self.assertEqual(code, 0)
            present_path = folder / PRESENT_NAME
            self.assertTrue(present_path.is_file())
            report = present_path.read_text(encoding="utf-8")
            self.assertIn("Mental model", report)
            self.assertIn("stills/still-001.png", report)

    def test_present_cli_accepts_a_lecture_folder(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw) / "lecture.lecture"
            folder.mkdir()
            write_document(_document(), folder)
            code = main(["present", str(folder)])
            self.assertEqual(code, 0)
            self.assertTrue((folder / PRESENT_NAME).is_file())

    def test_present_missing_document_is_a_user_error(self) -> None:
        code = main(["present", "/definitely/not/a/lecture.json"])
        self.assertEqual(code, 2)

    def test_present_cli_warns_when_section_matches_no_still(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            path = write_document(_document(), folder)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["sections"][0]["still_id"] = "missing-still"
            path.write_text(json.dumps(payload), encoding="utf-8")

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = main(["present", str(path)])

            self.assertEqual(code, 0)
            self.assertTrue((folder / PRESENT_NAME).is_file())
            self.assertIn("warning:", stderr.getvalue())
            self.assertIn("missing-still", stderr.getvalue())
            self.assertNotIn(
                "A hash table maps keys to values",
                (folder / PRESENT_NAME).read_text(encoding="utf-8"),
            )

    def test_write_present_creates_the_html_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            path = write_present(_document(), folder)
            self.assertEqual(path, folder / PRESENT_NAME)
            self.assertTrue(path.is_file())

    def test_present_to_another_folder_copies_still_images(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            source = folder / "lecture"
            source.mkdir()
            image = source / "stills" / "still-001.png"
            image.parent.mkdir()
            image.write_bytes(b"\x89PNG")
            path = write_document(_document(), source)
            target = folder / "elsewhere"
            code = main(["present", str(path), "-o", str(target)])
            self.assertEqual(code, 0)
            self.assertTrue((target / PRESENT_NAME).is_file())
            self.assertTrue((target / "stills" / "still-001.png").is_file())
