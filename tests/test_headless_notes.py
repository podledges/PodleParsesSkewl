from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from podleparsesskewl.cli import (
    _build_parser,
    format_retry,
    main,
    notes_preflight,
    quote_command,
)
from podleparsesskewl.config import AppConfig, find_recordings, load_config
from podleparsesskewl.deps import FFMPEG_SETUP, TRANSCRIBER_SETUP, lectures_dir_setup
from podleparsesskewl.document import Cue, LectureDocument, Section, SourceInfo, Still, Transcript
from podleparsesskewl.present import REVIEW_NAME, render_review
from podleparsesskewl.report import render_faithful_html


def _document() -> LectureDocument:
    return LectureDocument(
        title="Week 5 <system>",
        source=SourceInfo("Week5-System.mp4", 8.0, "sidecar:srt:Week5-System.srt"),
        stills=(
            Still("still-001", 1, 0.0, 4.0, "stills/still-001.png"),
            Still("still-002", 2, 4.0, 8.0, "stills/still-002.png"),
        ),
        transcript=Transcript(
            (
                Cue(1.0, 2.0, "um okay the bus grants the cpu.\nLine two stays."),
                Cue(5.0, 6.0, "Look at <this>."),
            ),
            "sidecar:srt:Week5-System.srt",
        ),
        sections=(
            Section("still-002", "Look at <this>.", (1,)),
            Section("still-001", "um okay the bus grants the cpu.\nLine two stays.", (0,)),
        ),
    )


def _ready_env() -> SimpleNamespace:
    found = SimpleNamespace(found=True)
    return SimpleNamespace(
        ffmpeg=found,
        ffprobe=found,
        can_transcribe_audio=True,
        can_parse_video=True,
    )


def _study_tree(root: Path) -> None:
    files = [
        root / "5 - CG2027" / "recordings" / "Week5-System.mp4",
        root / "2 - RTOS" / "recordings" / "Week4-Tasks.mp4",
        root / "4 - Image Processing and analysis" / "recordings" / "Week4-Filters.mp4",
        root / "5 - CG2027" / "recordings" / "Week4-Pipeline.mp4",
        root / "5 - CG2027" / "notes" / "Week5.txt",
    ]
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"mp4" if path.suffix == ".mp4" else b"text")


class FaithfulViewTests(unittest.TestCase):
    def test_faithful_view_keeps_every_still_and_does_not_rewrite_said(self) -> None:
        html = render_faithful_html(_document())
        faithful = html.split('id="shown-and-said"', 1)[1]
        first = faithful.index("stills/still-001.png")
        second = faithful.index("stills/still-002.png")
        self.assertLess(first, second)
        self.assertEqual(faithful.count('class="still"'), 2)
        self.assertIn('src="stills/still-001.png"', faithful)
        self.assertNotIn("/tmp/", faithful)
        self.assertIn("<p>um okay the bus grants the cpu.</p>", faithful)
        self.assertIn("<p>Line two stays.</p>", faithful)
        self.assertIn("&lt;this&gt;", faithful)
        self.assertNotIn("<this>", faithful)
        self.assertNotIn("In a nutshell", faithful)
        self.assertNotIn("<video", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertIn("00:00:00 - 00:00:04", faithful)
        self.assertIn('class="between"', faithful)
        self.assertIn('class="rule"', faithful)

    def test_a_silent_still_is_kept_and_not_merged(self) -> None:
        document = _document()
        silent = LectureDocument(
            title=document.title,
            source=document.source,
            stills=document.stills,
            transcript=document.transcript,
            sections=(Section("still-001", "", ()), document.sections[0]),
        )
        html = render_faithful_html(silent)
        self.assertEqual(html.count('class="still"'), 2)
        self.assertLess(html.index("stills/still-001.png"), html.index("stills/still-002.png"))
        self.assertIn("Look at", html)

    def test_review_page_carries_both_views(self) -> None:
        html = render_review(_document())
        teaching, faithful = html.split('id="shown-and-said"', 1)
        self.assertIn("Executive summary", teaching)
        self.assertIn("Mental model", teaching)
        self.assertIn('href="#teaching"', html)
        self.assertIn('href="#shown-and-said"', html)
        self.assertIn("stills/still-001.png", faithful)
        self.assertIn("stills/still-002.png", faithful)
        self.assertIn("<p>um okay the bus grants the cpu.</p>", faithful)
        self.assertNotIn("In a nutshell", faithful)


class SelectionTests(unittest.TestCase):
    def test_recursive_search_finds_one_nested_recording(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _study_tree(root)
            found = find_recordings(root, "Week5")
        self.assertEqual(len(found), 1)
        self.assertTrue(str(found[0]).endswith(str(Path("5 - CG2027") / "recordings" / "Week5-System.mp4")))

    def test_many_matches_are_listed_and_not_chosen(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _study_tree(root)
            found = find_recordings(root, "week4")
        self.assertEqual(len(found), 3)
        self.assertEqual(found, sorted(found, key=lambda path: path.as_posix().casefold()))
        self.assertTrue(all(path.is_absolute() for path in found))

    def test_course_folder_name_matches_recordings_under_it(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _study_tree(root)
            found = find_recordings(root, "CG2027")
        self.assertEqual(len(found), 2)
        self.assertTrue(all("CG2027" in str(path) for path in found))

    def test_windows_search_folder_with_spaces_translates_under_wsl(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _study_tree(root)
            windows = r"C:\Users\ayden\Documents\SCHOOL\NUS Y3S1"
            with mock.patch("podleparsesskewl.config.running_under_wsl", return_value=True):
                with mock.patch("podleparsesskewl.config.windows_path_to_wsl", return_value=str(root)):
                    found = find_recordings(Path(windows), "Week5")
        self.assertEqual(len(found), 1)

    def test_retry_command_quotes_the_study_path_for_both_shells(self) -> None:
        study = r"C:\Users\ayden\Documents\SCHOOL\NUS Y3S1"
        argv = ["notes", "--find", "Week5", "--in", study]
        windows = quote_command(["python", "-m", "podleparsesskewl", *argv], windows=True)
        posix = quote_command(["python3", "-m", "podleparsesskewl", *argv], windows=False)
        self.assertIn(f'"{study}"', windows)
        self.assertIn(f"'{study}'", posix)
        self.assertIn("NUS Y3S1", format_retry(argv))


class NotesContractTests(unittest.TestCase):
    def test_notes_rejects_the_file_picker(self) -> None:
        parser = _build_parser()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["notes", "--pick"])
        picked = parser.parse_args(["parse", "--pick"])
        self.assertTrue(picked.pick)
        self.assertFalse(hasattr(parser.parse_args(["notes", "file.mp4"]), "pick"))

    def test_preflight_stops_before_any_work_and_prints_the_retry(self) -> None:
        missing = SimpleNamespace(found=False)
        env = SimpleNamespace(
            ffmpeg=missing,
            ffprobe=missing,
            can_transcribe_audio=False,
            can_parse_video=False,
        )
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            output = folder / "should-not-exist"
            argv = [
                "notes",
                str(folder / "missing.mp4"),
                "--lectures-dir",
                str(folder / "absent-lectures"),
                "-o",
                str(output),
            ]
            stdout, stderr = io.StringIO(), io.StringIO()
            with mock.patch("podleparsesskewl.cli.inspect_environment", return_value=env):
                with mock.patch("podleparsesskewl.cli.parse_and_present") as run:
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        code = main(argv)
        self.assertEqual(code, 1)
        run.assert_not_called()
        self.assertFalse(output.exists())
        err = stderr.getvalue()
        self.assertIn(FFMPEG_SETUP, err)
        self.assertIn(TRANSCRIBER_SETUP, err)
        self.assertIn("absent-lectures", err)
        self.assertIn("Retry:", err)
        self.assertIn("NUS Y3S1", lectures_dir_setup(Path("absent-lectures")))
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["error"], "preflight")
        self.assertEqual(payload["missing"], ["ffmpeg", "ffprobe", "transcriber", "lectures_dir"])
        self.assertIn("notes", payload["retry"])
        self.assertNotIn("{", err)

    def test_zero_and_many_matches_fail_without_guessing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _study_tree(root)
            stdout, stderr = io.StringIO(), io.StringIO()
            with mock.patch("podleparsesskewl.cli.notes_preflight", return_value=()):
                with mock.patch("podleparsesskewl.cli.parse_and_present") as run:
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        code = main(["notes", "--find", "Week4", "--in", str(root), "--lectures-dir", str(root)])
            self.assertEqual(code, 2)
            run.assert_not_called()
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["error"], "selection")
            self.assertEqual(len(payload["matches"]), 3)
            err = stderr.getvalue()
            for match in payload["matches"]:
                self.assertIn(match, err)
            self.assertIn("Week4-Tasks.mp4", err)
            self.assertIn("Week4-Filters.mp4", err)
            self.assertIn("Week4-Pipeline.mp4", err)

            stdout, stderr = io.StringIO(), io.StringIO()
            with mock.patch("podleparsesskewl.cli.notes_preflight", return_value=()):
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = main(["notes", "--find", "Week9", "--in", str(root), "--lectures-dir", str(root)])
            self.assertEqual(code, 2)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["matches"], [])
            self.assertIn("no Recording matched", stderr.getvalue())

    def test_successful_notes_json_names_the_one_page_and_keeps_human_text_on_stderr(self) -> None:
        document = _document()
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            recording = folder / "Week5-System.mp4"
            recording.write_bytes(b"mp4")
            output = folder / "out"
            review = output / REVIEW_NAME
            result = SimpleNamespace(
                parse=SimpleNamespace(
                    document_path=output / "lecture.json",
                    html_path=output / "lecture.html",
                    markdown_path=output / "lecture.md",
                    transcript_path=output / "transcript.md",
                    document=document,
                ),
                present=SimpleNamespace(
                    present_path=output / "lecture.present.html",
                    pairing_problems=("section still_id 'missing' matches no Still",),
                ),
                archive=None,
                review_path=review,
                recording=recording,
            )
            config = AppConfig(lectures_dir=folder, lectures_dir_source="test", archive_after_notes=False)
            stdout, stderr = io.StringIO(), io.StringIO()
            with mock.patch("podleparsesskewl.cli.notes_preflight", return_value=()):
                with mock.patch("podleparsesskewl.cli.load_config", return_value=config):
                    with mock.patch("podleparsesskewl.cli.parse_and_present", return_value=result) as run:
                        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                            code = main(["notes", str(recording), "--no-archive"])
        self.assertEqual(code, 0)
        self.assertIs(run.call_args.kwargs["archive"], False)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["schema"], "podleparsesskewl.notes/v1")
        self.assertEqual(payload["open"], str(review.resolve()))
        self.assertEqual(payload["artifacts"]["review"], str(review.resolve()))
        self.assertIsNone(payload["archive"])
        err = stderr.getvalue()
        self.assertIn("Archive   skipped", err)
        self.assertIn("Review", err)
        self.assertIn("warning:", err)
        self.assertNotIn("podleparsesskewl.notes/v1", err)
        self.assertNotIn('"open"', err)

    def test_notes_preflight_names_only_what_is_missing(self) -> None:
        ready = _ready_env()
        config = AppConfig(lectures_dir=Path("."), lectures_dir_source="test")
        self.assertEqual(notes_preflight(config, env=ready), ())
        broken = SimpleNamespace(
            ffmpeg=SimpleNamespace(found=True),
            ffprobe=SimpleNamespace(found=False),
            can_transcribe_audio=True,
        )
        self.assertEqual(notes_preflight(config, env=broken), ("ffprobe",))

    def test_explicit_path_and_latest_still_parse(self) -> None:
        parser = _build_parser()
        latest = parser.parse_args(["notes", "--latest"])
        self.assertTrue(latest.latest)
        self.assertIsNone(latest.recording)
        explicit = parser.parse_args(["notes", "file.mp4"])
        self.assertEqual(explicit.recording, Path("file.mp4"))
        self.assertIsNone(explicit.find)


class ArchiveDefaultTests(unittest.TestCase):
    def test_omitted_config_key_leaves_archive_off(self) -> None:
        env = {
            key: value
            for key, value in os.environ.items()
            if key != "PODLEPARSESSKEWL_LECTURES_DIR"
        }
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("podleparsesskewl.config._find_config", return_value=None):
                with mock.patch("podleparsesskewl.config.running_under_wsl", return_value=False):
                    config = load_config()
        self.assertFalse(config.archive_after_notes)


if __name__ == "__main__":
    unittest.main()
