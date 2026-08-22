from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from podleparsesskewl.cli import main
from podleparsesskewl.config import AppConfig
from podleparsesskewl.workflow import build_notes_argv, build_parse_argv, suggested_output_path


class GuiCommandBoundaryTests(unittest.TestCase):
    def test_parse_button_runs_the_parse_command(self) -> None:
        self.assertEqual(build_parse_argv("/tmp/a.mp4"), ["parse", "/tmp/a.mp4"])
        self.assertEqual(
            build_parse_argv("/tmp/a.mp4", "/tmp/out", "/tmp/a.srt"),
            ["parse", "/tmp/a.mp4", "--output", "/tmp/out", "--transcript", "/tmp/a.srt"],
        )

    def test_parse_plus_notes_button_runs_the_notes_command(self) -> None:
        self.assertEqual(build_notes_argv("/tmp/a.mp4"), ["notes", "/tmp/a.mp4", "--archive"])
        self.assertEqual(
            build_notes_argv("/tmp/a.mp4", "/tmp/out", "/tmp/a.srt", "/tmp/arch", True),
            [
                "notes",
                "/tmp/a.mp4",
                "--output",
                "/tmp/out",
                "--transcript",
                "/tmp/a.srt",
                "--archive-dir",
                "/tmp/arch",
                "--archive",
            ],
        )
        self.assertEqual(
            build_notes_argv("/tmp/a.mp4", archive=False),
            ["notes", "/tmp/a.mp4", "--no-archive"],
        )

    def test_suggested_output_follows_configured_default_parent(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw) / "reviews"
            parent.mkdir()
            config_file = Path(raw) / "pps.toml"
            config_file.write_text(f'output_dir = "{parent.as_posix()}"\n', encoding="utf-8")
            recording = str(Path(raw) / "talk.mp4")
            with mock.patch("podleparsesskewl.workflow.load_config") as loaded:
                from podleparsesskewl.config import load_config

                loaded.return_value = load_config(config_path=config_file)
                self.assertEqual(suggested_output_path(recording), str(parent / "talk.lecture"))

    def test_cli_accepts_the_gui_parse_argv(self) -> None:
        code = main(build_parse_argv("/definitely/not/a/recording.mp4"))
        self.assertEqual(code, 2)

    def test_cli_accepts_the_gui_notes_argv(self) -> None:
        code = main(build_notes_argv("/definitely/not/a/recording.mp4", archive=False))
        self.assertEqual(code, 2)
        code = main(build_notes_argv("/definitely/not/a/recording.mp4", archive=True))
        self.assertEqual(code, 2)

    def test_gui_checked_archive_overrides_config_skip(self) -> None:
        result = SimpleNamespace(
            parse=SimpleNamespace(
                document_path=Path("/tmp/out/lecture.json"),
                html_path=Path("/tmp/out/lecture.ez.html"),
                markdown_path=Path("/tmp/out/lecture.md"),
                document=SimpleNamespace(title="Lecture", stills=(), transcript=SimpleNamespace(cues=())),
            ),
            present=SimpleNamespace(present_path=Path("/tmp/out/lecture.present.html"), pairing_problems=()),
            archive=None,
        )
        config = AppConfig(
            lectures_dir=Path("/tmp"),
            lectures_dir_source="test",
            archive_after_notes=False,
        )
        with mock.patch("podleparsesskewl.cli.load_config", return_value=config):
            with mock.patch("podleparsesskewl.cli.parse_and_present", return_value=result) as run:
                code = main(build_notes_argv("/tmp/a.mp4", archive=True))
        self.assertEqual(code, 0)
        self.assertIs(run.call_args.kwargs["archive"], True)
