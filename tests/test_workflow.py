from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from podleparsesskewl.config import load_config
from podleparsesskewl.document import Cue, LectureDocument, Section, SourceInfo, Still, Transcript
from podleparsesskewl.pipeline import ParseOptions, ParseResult, write_document
from podleparsesskewl.present import PRESENT_NAME
from podleparsesskewl.workflow import parse_and_present, resolve_archive_dir, resolve_output_dir


def _document() -> LectureDocument:
    return LectureDocument(
        title="Hash tables",
        source=SourceInfo("lecture.mp4", 4.0, "sidecar:srt:lecture.srt"),
        stills=(Still("still-001", 1, 0.0, 4.0, "stills/still-001.png"),),
        transcript=Transcript((Cue(1.0, 2.0, "A hash table maps keys to values."),), "sidecar:srt:lecture.srt"),
        sections=(Section("still-001", "A hash table maps keys to values.", (0,)),),
    )


class DefaultOutputTests(unittest.TestCase):
    def test_explicit_output_is_the_lecture_folder(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            recording = Path(raw) / "talk.mp4"
            chosen = Path(raw) / "chosen"
            self.assertEqual(resolve_output_dir(recording, chosen), chosen)

    def test_configured_output_dir_is_a_parent_for_stem_lecture(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw) / "reviews"
            parent.mkdir()
            config_file = Path(raw) / "pps.toml"
            config_file.write_text(f'output_dir = "{parent.as_posix()}"\n', encoding="utf-8")
            config = load_config(config_path=config_file)
            recording = Path(raw) / "talk.mp4"
            self.assertEqual(resolve_output_dir(recording, None, config), parent / "talk.lecture")

    def test_env_output_dir_beats_the_sibling_default(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw) / "from-env"
            parent.mkdir()
            env = {
                key: value
                for key, value in os.environ.items()
                if key not in {"PODLEPARSESSKEWL_LECTURES_DIR", "PODLEPARSESSKEWL_OUTPUT_DIR"}
            }
            env["PODLEPARSESSKEWL_OUTPUT_DIR"] = str(parent)
            with mock.patch.dict(os.environ, env, clear=True):
                with mock.patch("podleparsesskewl.config._find_config", return_value=None):
                    config = load_config()
            recording = Path(raw) / "talk.mp4"
            self.assertEqual(resolve_output_dir(recording, None, config), parent / "talk.lecture")

    def test_unset_output_dir_uses_the_sibling_lecture_folder(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            recording = Path(raw) / "talk.mp4"
            recording.write_bytes(b"")
            env = {
                key: value
                for key, value in os.environ.items()
                if key not in {"PODLEPARSESSKEWL_LECTURES_DIR", "PODLEPARSESSKEWL_OUTPUT_DIR"}
            }
            with mock.patch.dict(os.environ, env, clear=True):
                with mock.patch("podleparsesskewl.config._find_config", return_value=None):
                    config = load_config()
            self.assertEqual(
                resolve_output_dir(recording, None, config),
                recording.resolve().parent / "talk.lecture",
            )

    def test_archive_dir_falls_back_beside_the_recording(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            recording = Path(raw) / "talk.mp4"
            env = {
                key: value
                for key, value in os.environ.items()
                if key not in {"PODLEPARSESSKEWL_LECTURES_DIR", "PODLEPARSESSKEWL_ARCHIVE_DIR"}
            }
            with mock.patch.dict(os.environ, env, clear=True):
                with mock.patch("podleparsesskewl.config._find_config", return_value=None):
                    config = load_config()
            self.assertEqual(resolve_archive_dir(recording, None, config), recording.resolve().parent / "archive")


class ParseAndPresentTests(unittest.TestCase):
    def test_notes_flow_writes_present_html_then_moves_the_input(self) -> None:
        document = _document()
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            recording = folder / "lecture.mp4"
            sidecar = folder / "lecture.srt"
            recording.write_bytes(b"mp4")
            sidecar.write_text("captions", encoding="utf-8")
            output = folder / "out"
            archive = folder / "filed"

            def fake_parse(path: Path, options: ParseOptions, env=None) -> ParseResult:
                output.mkdir(parents=True, exist_ok=True)
                (output / "stills").mkdir(exist_ok=True)
                (output / "stills" / "still-001.png").write_bytes(b"\x89PNG")
                document_path = write_document(document, output)
                html_path = output / "lecture.html"
                md_path = output / "lecture.md"
                html_path.write_text("<html></html>", encoding="utf-8")
                md_path.write_text("# md\n", encoding="utf-8")
                return ParseResult(
                    document=document,
                    document_path=document_path,
                    html_path=html_path,
                    markdown_path=md_path,
                )

            with mock.patch("podleparsesskewl.workflow.parse_recording", side_effect=fake_parse):
                result = parse_and_present(
                    recording,
                    output=output,
                    options=ParseOptions(output_dir=output, sidecar=sidecar),
                    archive=True,
                    archive_dir=archive,
                )

            self.assertTrue(result.present.present_path.is_file())
            self.assertEqual(result.present.present_path.name, PRESENT_NAME)
            self.assertIn("Mental model", result.present.present_path.read_text(encoding="utf-8"))
            self.assertFalse(recording.exists())
            self.assertFalse(sidecar.exists())
            self.assertIsNotNone(result.archive)
            self.assertTrue((result.archive.run_dir / "lecture.mp4").is_file())
            self.assertTrue((output / "lecture.json").is_file())

    def test_failed_parse_leaves_the_recording_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            recording = folder / "lecture.mp4"
            recording.write_bytes(b"mp4")
            with mock.patch(
                "podleparsesskewl.workflow.parse_recording",
                side_effect=RuntimeError("boom"),
            ):
                with self.assertRaises(RuntimeError):
                    parse_and_present(
                        recording,
                        output=folder / "out",
                        archive=True,
                        archive_dir=folder / "archive",
                    )
            self.assertTrue(recording.is_file())
            self.assertFalse((folder / "archive").exists())

    def test_no_archive_leaves_the_recording_in_place(self) -> None:
        document = _document()
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            recording = folder / "lecture.mp4"
            recording.write_bytes(b"mp4")
            output = folder / "out"

            def fake_parse(path: Path, options: ParseOptions, env=None) -> ParseResult:
                output.mkdir(parents=True, exist_ok=True)
                document_path = write_document(document, output)
                html_path = output / "lecture.html"
                md_path = output / "lecture.md"
                html_path.write_text("html", encoding="utf-8")
                md_path.write_text("md", encoding="utf-8")
                return ParseResult(document, document_path, html_path, md_path)

            with mock.patch("podleparsesskewl.workflow.parse_recording", side_effect=fake_parse):
                result = parse_and_present(recording, output=output, archive=False)

            self.assertTrue(recording.is_file())
            self.assertIsNone(result.archive)
            self.assertTrue(result.present.present_path.is_file())
