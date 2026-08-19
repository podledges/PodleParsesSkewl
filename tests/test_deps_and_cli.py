from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from podleparsesskewl.cli import main
from podleparsesskewl.config import DEFAULT_LECTURES_DIR, load_config, windows_path_to_wsl
from podleparsesskewl.deps import _ffprobe_status, format_doctor, inspect_environment


def _render_fixture_document():
    from podleparsesskewl.document import (
        Cue,
        LectureDocument,
        Section,
        SourceInfo,
        Still,
        Transcript,
    )

    return LectureDocument(
        title="Rendered",
        source=SourceInfo("lecture.mp4", 4.0, "sidecar:srt:lecture.srt"),
        stills=(Still("still-001", 1, 0.0, 4.0, "stills/still-001.png"),),
        transcript=Transcript((Cue(1.0, 2.0, "Said here."),), "sidecar:srt:lecture.srt"),
        sections=(Section("still-001", "Said here.", (0,)),),
    )


class ConfigTests(unittest.TestCase):
    def test_default_lectures_dir_is_the_windows_path(self) -> None:
        env = {key: value for key, value in os.environ.items() if key != "PODLEPARSESSKEWL_LECTURES_DIR"}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("podleparsesskewl.config._find_config", return_value=None):
                with mock.patch("podleparsesskewl.config.running_under_wsl", return_value=False):
                    config = load_config()
        self.assertEqual(str(config.lectures_dir), DEFAULT_LECTURES_DIR)
        self.assertEqual(config.lectures_dir_source, "default")

    def test_env_overrides_default_lectures_dir(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with mock.patch.dict(os.environ, {"PODLEPARSESSKEWL_LECTURES_DIR": raw}):
                config = load_config()
            self.assertEqual(config.lectures_dir, Path(raw))
            self.assertEqual(config.lectures_dir_source, "env")

    def test_explicit_config_file_beats_the_environment(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            chosen = folder / "chosen"
            chosen.mkdir()
            config_file = folder / "my.toml"
            config_file.write_text(f'lectures_dir = "{chosen.as_posix()}"\n', encoding="utf-8")
            with mock.patch.dict(
                os.environ, {"PODLEPARSESSKEWL_LECTURES_DIR": str(folder / "stale")}
            ):
                config = load_config(config_path=config_file)
        self.assertEqual(config.lectures_dir, chosen)
        self.assertIn("config:", config.lectures_dir_source)

    def test_config_file_without_lectures_dir_falls_back_to_the_environment(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            config_file = folder / "my.toml"
            config_file.write_text("# nothing set here\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"PODLEPARSESSKEWL_LECTURES_DIR": raw}):
                config = load_config(config_path=config_file)
        self.assertEqual(config.lectures_dir, Path(raw))
        self.assertEqual(config.lectures_dir_source, "env")

    def test_windows_lecture_dir_is_translated_under_wsl(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            config_file = Path(raw) / "my.toml"
            config_file.write_text(
                'lectures_dir = "C:\\\\Users\\\\ayden\\\\Videos\\\\Lectures"\n', encoding="utf-8"
            )
            with mock.patch("podleparsesskewl.config.running_under_wsl", return_value=True):
                config = load_config(config_path=config_file)
        self.assertEqual(config.lectures_dir, Path("/mnt/c/Users/ayden/Videos/Lectures"))
        self.assertIn("C:\\Users\\ayden\\Videos\\Lectures", config.lectures_dir_source)

    def test_windows_path_translation_leaves_posix_paths_alone(self) -> None:
        self.assertEqual(
            windows_path_to_wsl(r"C:\Users\ayden\Videos\Lectures"),
            "/mnt/c/Users/ayden/Videos/Lectures",
        )
        self.assertEqual(windows_path_to_wsl("D:/Media/Lectures"), "/mnt/d/Media/Lectures")
        self.assertIsNone(windows_path_to_wsl("/mnt/c/Users/ayden/Videos/Lectures"))
        self.assertIsNone(windows_path_to_wsl("./local"))


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

    def test_ffprobe_is_found_next_to_a_windows_ffmpeg_exe(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            ffmpeg = folder / "ffmpeg.exe"
            ffmpeg.write_bytes(b"")
            probe = folder / "ffprobe.exe"
            probe.write_bytes(b"")
            with mock.patch("podleparsesskewl.deps._resolve_binary", return_value=(None, "")):
                with mock.patch(
                    "podleparsesskewl.deps._run_version", return_value="ffprobe version test"
                ):
                    status = _ffprobe_status(ffmpeg)
        self.assertTrue(status.found)
        self.assertEqual(status.path, probe)

    def test_ffprobe_is_still_found_next_to_a_suffixless_ffmpeg(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            ffmpeg = folder / "ffmpeg"
            ffmpeg.write_bytes(b"")
            probe = folder / "ffprobe"
            probe.write_bytes(b"")
            with mock.patch("podleparsesskewl.deps._resolve_binary", return_value=(None, "")):
                with mock.patch(
                    "podleparsesskewl.deps._run_version", return_value="ffprobe version test"
                ):
                    status = _ffprobe_status(ffmpeg)
        self.assertTrue(status.found)
        self.assertEqual(status.path, probe)

    def test_unusable_ffmpeg_override_names_the_variable(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            missing = str(Path(raw) / "nowhere" / "ffmpeg")
            with mock.patch.dict(
                os.environ, {"PODLEPARSESSKEWL_FFMPEG": missing}, clear=False
            ):
                os.environ.pop("PODLEPARSESSKEWL_FFPROBE", None)
                with mock.patch(
                    "podleparsesskewl.deps.shutil.which", return_value="/usr/bin/ffmpeg"
                ):
                    env = inspect_environment()
        self.assertFalse(env.ffmpeg.found)
        self.assertIn("PODLEPARSESSKEWL_FFMPEG", env.ffmpeg.detail)
        self.assertIn(missing, env.ffmpeg.detail)
        self.assertIn("PODLEPARSESSKEWL_FFMPEG", format_doctor(env))

    def test_windows_ffmpeg_override_is_translated_under_wsl(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            binary = Path(raw) / "ffmpeg.exe"
            binary.write_bytes(b"")
            with mock.patch.dict(
                os.environ,
                {"PODLEPARSESSKEWL_FFMPEG": r"C:\ffmpeg\bin\ffmpeg.exe"},
                clear=False,
            ):
                os.environ.pop("PODLEPARSESSKEWL_FFPROBE", None)
                with mock.patch("podleparsesskewl.deps.running_under_wsl", return_value=True):
                    with mock.patch(
                        "podleparsesskewl.deps.windows_path_to_wsl", return_value=str(binary)
                    ):
                        with mock.patch(
                            "podleparsesskewl.deps._run_version", return_value="ffmpeg version test"
                        ):
                            with mock.patch(
                                "podleparsesskewl.deps.shutil.which", return_value=None
                            ):
                                env = inspect_environment()
        self.assertTrue(env.ffmpeg.found)
        self.assertEqual(env.ffmpeg.path, binary)

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

    def test_render_to_another_folder_copies_the_still_images(self) -> None:
        from podleparsesskewl.pipeline import write_document

        document = _render_fixture_document()
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            source = folder / "lecture"
            source.mkdir()
            image = source / "stills" / "still-001.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"\x89PNG image bytes")
            path = write_document(document, source)
            target = folder / "elsewhere"

            code = main(["render", str(path), "-o", str(target)])

            self.assertEqual(code, 0)
            html = (target / "lecture.html").read_text(encoding="utf-8")
            self.assertIn('src="stills/still-001.png"', html)
            copied = target / "stills" / "still-001.png"
            self.assertTrue(copied.is_file(), "rendered HTML points at an image that was not copied")
            self.assertEqual(copied.read_bytes(), image.read_bytes())
            self.assertTrue((target / "lecture.json").is_file())

    def test_render_leaves_the_source_document_untouched(self) -> None:
        from podleparsesskewl.pipeline import write_document

        document = _render_fixture_document()
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            path = write_document(document, folder)
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    '"title": "Rendered"', '"title": "Rendered",\n  "notes": "hand added"'
                ),
                encoding="utf-8",
            )
            before = path.read_text(encoding="utf-8")

            code = main(["render", str(path)])

            self.assertEqual(code, 0)
            self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_render_output_over_an_existing_file_is_a_user_error(self) -> None:
        from podleparsesskewl.pipeline import write_document

        document = _render_fixture_document()
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            path = write_document(document, folder)
            blocker = folder / "blocker"
            blocker.write_text("not a directory", encoding="utf-8")
            code = main(["render", str(path), "-o", str(blocker)])
        self.assertEqual(code, 2)

    @unittest.skipIf(
        hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores directory permissions"
    )
    def test_render_into_a_read_only_folder_is_a_user_error(self) -> None:
        from podleparsesskewl.pipeline import write_document

        document = _render_fixture_document()
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            path = write_document(document, folder)
            locked = folder / "locked"
            locked.mkdir()
            locked.chmod(0o500)
            try:
                code = main(["render", str(path), "-o", str(locked / "out")])
            finally:
                locked.chmod(0o700)
        self.assertEqual(code, 2)

    def test_render_rejects_a_wrong_typed_document(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "lecture.json"
            payload = _render_fixture_document().to_json_dict()
            payload["stills"][0]["start_seconds"] = "0 seconds in"
            path.write_text(json.dumps(payload), encoding="utf-8")
            code = main(["render", str(path)])
        self.assertEqual(code, 2)

    def test_render_rejects_non_finite_document_numbers(self) -> None:
        cases = {
            "literal Infinity": ("stills", "start_seconds", float("inf")),
            "overflowing string": ("stills", "start_seconds", "1e400"),
            "infinite index": ("stills", "index", float("inf")),
            "infinite duration": ("source", "duration_seconds", float("-inf")),
        }
        for label, (section, field, value) in cases.items():
            with self.subTest(case=label):
                payload = _render_fixture_document().to_json_dict()
                if section == "stills":
                    payload["stills"][0][field] = value
                else:
                    payload["source"][field] = value
                with tempfile.TemporaryDirectory() as raw:
                    path = Path(raw) / "lecture.json"
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    code = main(["render", str(path)])
                self.assertEqual(code, 2)

    def test_render_to_another_folder_preserves_unknown_document_fields(self) -> None:
        from podleparsesskewl.pipeline import write_document

        document = _render_fixture_document()
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            source = folder / "lecture"
            source.mkdir()
            image = source / "stills" / "still-001.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"\x89PNG")
            path = write_document(document, source)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["notes"] = "hand added"
            payload["stills"][0]["caption"] = "annotated by an agent"
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            target = folder / "elsewhere"

            code = main(["render", str(path), "-o", str(target)])

            self.assertEqual(code, 0)
            copied = json.loads((target / "lecture.json").read_text(encoding="utf-8"))
            self.assertEqual(copied["notes"], "hand added")
            self.assertEqual(copied["stills"][0]["caption"], "annotated by an agent")

    def test_render_rejects_a_structurally_invalid_document(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "lecture.json"
            path.write_text('{"title": "x"}', encoding="utf-8")
            code = main(["render", str(path)])
        self.assertEqual(code, 2)
