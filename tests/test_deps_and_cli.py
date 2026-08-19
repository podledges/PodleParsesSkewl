from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from podleparsesskewl.cli import main
from podleparsesskewl.config import DEFAULT_LECTURES_DIR, load_config
from podleparsesskewl.deps import inspect_environment


class ConfigTests(unittest.TestCase):
    def test_default_lectures_dir_is_the_windows_path(self) -> None:
        env = {key: value for key, value in os.environ.items() if key != "PODLEPARSESSKEWL_LECTURES_DIR"}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("podleparsesskewl.config._find_config", return_value=None):
                config = load_config()
        self.assertEqual(str(config.lectures_dir), DEFAULT_LECTURES_DIR)
        self.assertEqual(config.lectures_dir_source, "default")

    def test_env_overrides_default_lectures_dir(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with mock.patch.dict(os.environ, {"PODLEPARSESSKEWL_LECTURES_DIR": raw}):
                config = load_config()
            self.assertEqual(config.lectures_dir, Path(raw))
            self.assertEqual(config.lectures_dir_source, "env")


class DoctorTests(unittest.TestCase):
    def test_doctor_reports_missing_ffmpeg_without_crashing(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PODLEPARSESSKEWL_FFMPEG", None)
            os.environ.pop("PODLEPARSESSKEWL_FFPROBE", None)
            with mock.patch("podleparsesskewl.deps.shutil.which", return_value=None):
                env = inspect_environment()
        self.assertFalse(env.ffmpeg.found)
        self.assertFalse(env.can_parse_video)

    def test_cli_doctor_exits_nonzero_when_ffmpeg_is_missing(self) -> None:
        with mock.patch("podleparsesskewl.cli.inspect_environment") as inspect:
            inspect.return_value.can_parse_video = False
            inspect.return_value.ffmpeg.found = False
            inspect.return_value.ffprobe.found = False
            inspect.return_value.transcriber.found = False
            with mock.patch("podleparsesskewl.cli.format_doctor", return_value="doctor"):
                code = main(["doctor"])
        self.assertEqual(code, 1)

    def test_parse_without_recording_explains_usage(self) -> None:
        code = main(["parse"])
        self.assertEqual(code, 2)

    def test_list_missing_directory_is_a_user_error(self) -> None:
        code = main(["list", "/definitely/not/a/real/lectures/dir"])
        self.assertEqual(code, 2)

    def test_render_rebuilds_plain_views_from_lecture_json(self) -> None:
        from podleparsesskewl.document import (
            Cue,
            LectureDocument,
            Section,
            SourceInfo,
            Still,
            Transcript,
        )
        from podleparsesskewl.pipeline import write_document

        document = LectureDocument(
            title="Rendered",
            source=SourceInfo("lecture.mp4", 4.0, "sidecar:srt:lecture.srt"),
            stills=(Still("still-001", 1, 0.0, 4.0, "stills/still-001.png"),),
            transcript=Transcript((Cue(1.0, 2.0, "Said here."),), "sidecar:srt:lecture.srt"),
            sections=(Section("still-001", "Said here.", (0,)),),
        )
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            path = write_document(document, folder)
            code = main(["render", str(path)])
            self.assertEqual(code, 0)
            html = (folder / "lecture.html").read_text(encoding="utf-8")
            self.assertIn("Said here.", html)
            self.assertIn("<hr>", html)
