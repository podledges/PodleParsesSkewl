from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from podleparsesskewl.deps import Environment, ToolStatus
from podleparsesskewl.errors import PpsError
from podleparsesskewl.pipeline import ParseOptions, parse_recording
from podleparsesskewl.report import render_html

FIXTURES = Path(__file__).parent / "fixtures"


def _ffmpeg() -> str | None:
    override = os.environ.get("PODLEPARSESSKEWL_FFMPEG")
    if override and Path(override).is_file():
        return override
    return shutil.which("ffmpeg")


def _make_two_still_recording(folder: Path, ffmpeg: str) -> Path:
    dest = folder / "lecture.mp4"
    command = [
        ffmpeg,
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=red:s=320x240:d=4,format=yuv420p",
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:s=320x240:d=4,format=yuv420p",
        "-filter_complex",
        "[0:v][1:v]concat=n=2:v=1:a=0[v]",
        "-map",
        "[v]",
        "-c:v",
        "mpeg4",
        "-y",
        str(dest),
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"ffmpeg fixture failed: {result.stderr}")
    sidecar = folder / "lecture.srt"
    sidecar.write_text((FIXTURES / "sample.srt").read_text(encoding="utf-8"))
    return dest


class CopyStillImagesTests(unittest.TestCase):
    def _document(self, image: str):
        from podleparsesskewl.document import (
            Cue,
            LectureDocument,
            Section,
            SourceInfo,
            Still,
            Transcript,
        )

        return LectureDocument(
            title="Lecture",
            source=SourceInfo("lecture.mp4", 4.0, "sidecar:srt:lecture.srt"),
            stills=(Still("still-001", 1, 0.0, 4.0, image),),
            transcript=Transcript((Cue(1.0, 2.0, "Said."),), "sidecar:srt:lecture.srt"),
            sections=(Section("still-001", "Said.", (0,)),),
        )

    def test_backslash_traversal_is_rejected(self) -> None:
        from podleparsesskewl.pipeline import copy_still_images

        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            source = folder / "lecture"
            source.mkdir()
            target = folder / "out"
            target.mkdir()
            for reference in (
                r"stills\..\..\evil.png",
                "stills/../../evil.png",
                r"..\evil.png",
            ):
                with self.subTest(reference=reference):
                    with self.assertRaises(PpsError):
                        copy_still_images(self._document(reference), source, target)
            self.assertEqual(list(folder.glob("evil.png")), [])

    def test_an_absolute_image_reference_is_reported_not_skipped(self) -> None:
        from podleparsesskewl.pipeline import copy_still_images

        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            source = folder / "lecture"
            source.mkdir()
            target = folder / "out"
            target.mkdir()
            absolute = folder / "elsewhere" / "still-001.png"
            problems = copy_still_images(self._document(str(absolute)), source, target)
        self.assertEqual(len(problems), 1)
        self.assertIn(str(absolute), problems[0])
        self.assertIn("absolute", problems[0])

    def test_a_missing_image_reference_is_reported(self) -> None:
        from podleparsesskewl.pipeline import copy_still_images

        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            source = folder / "lecture"
            source.mkdir()
            target = folder / "out"
            target.mkdir()
            problems = copy_still_images(
                self._document("stills/still-001.png"), source, target
            )
        self.assertEqual(len(problems), 1)
        self.assertIn("stills/still-001.png", problems[0])

    def test_a_plain_relative_image_is_copied(self) -> None:
        from podleparsesskewl.pipeline import copy_still_images

        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            source = folder / "lecture"
            (source / "stills").mkdir(parents=True)
            (source / "stills" / "still-001.png").write_bytes(b"\x89PNG")
            target = folder / "out"
            target.mkdir()
            problems = copy_still_images(
                self._document("stills/still-001.png"), source, target
            )
            self.assertEqual(problems, [])
            self.assertTrue((target / "stills" / "still-001.png").is_file())


class WorkFolderTests(unittest.TestCase):
    def test_parse_leaves_a_preexisting_work_folder_alone(self) -> None:
        from types import SimpleNamespace
        from unittest import mock

        from podleparsesskewl.stills import (
            DEFAULT_SAMPLE_HEIGHT,
            DEFAULT_SAMPLE_WIDTH,
            FrameSignature,
        )

        frames = [
            FrameSignature(
                time_seconds=float(index),
                width=DEFAULT_SAMPLE_WIDTH,
                height=DEFAULT_SAMPLE_HEIGHT,
                samples=bytes([0]) * (DEFAULT_SAMPLE_WIDTH * DEFAULT_SAMPLE_HEIGHT),
            )
            for index in range(3)
        ]
        env = Environment(
            ffmpeg=ToolStatus("ffmpeg", True, Path("/usr/bin/ffmpeg"), "stub"),
            ffprobe=ToolStatus("ffprobe", True, Path("/usr/bin/ffprobe"), "stub"),
            transcriber=ToolStatus("transcriber", False, None, "none"),
        )

        def fake_still(_recording, _timestamp, dest: Path, _env):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"\x89PNG")

        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            recording = folder / "lecture.mp4"
            recording.write_bytes(b"stub")
            (folder / "lecture.srt").write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nHello.\n", encoding="utf-8"
            )
            output = folder / "out"
            precious = output / "_work" / "notes.txt"
            precious.parent.mkdir(parents=True)
            precious.write_text("someone else's file", encoding="utf-8")

            with mock.patch(
                "podleparsesskewl.pipeline.probe_recording",
                return_value=SimpleNamespace(
                    duration_seconds=3.0,
                    width=640,
                    height=480,
                    has_audio=True,
                    has_video=True,
                ),
            ):
                with mock.patch(
                    "podleparsesskewl.pipeline.sample_signatures", return_value=frames
                ):
                    with mock.patch(
                        "podleparsesskewl.pipeline.extract_still_png", side_effect=fake_still
                    ):
                        parse_recording(
                            recording, ParseOptions(output_dir=output), env=env
                        )

            self.assertTrue(precious.is_file())
            self.assertEqual(precious.read_text(encoding="utf-8"), "someone else's file")
            self.assertEqual(
                [path.name for path in output.glob("_work-*")], [], "run scratch was left behind"
            )


class FailedParseCleanupTests(unittest.TestCase):
    def test_a_failing_parse_does_not_leave_scratch_folders_behind(self) -> None:
        from types import SimpleNamespace
        from unittest import mock

        env = Environment(
            ffmpeg=ToolStatus("ffmpeg", True, Path("/usr/bin/ffmpeg"), "stub"),
            ffprobe=ToolStatus("ffprobe", True, Path("/usr/bin/ffprobe"), "stub"),
            transcriber=ToolStatus("transcriber", False, None, "none"),
        )
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            recording = folder / "lecture.mp4"
            recording.write_bytes(b"stub")
            (folder / "lecture.srt").write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nHello.\n", encoding="utf-8"
            )
            output = folder / "out"

            def explode(*_args, **_kwargs):
                raise PpsError("ffmpeg frame sampling failed")

            with mock.patch(
                "podleparsesskewl.pipeline.probe_recording",
                return_value=SimpleNamespace(
                    duration_seconds=3.0,
                    width=640,
                    height=480,
                    has_audio=True,
                    has_video=True,
                ),
            ):
                with mock.patch(
                    "podleparsesskewl.pipeline.sample_signatures", side_effect=explode
                ):
                    for _attempt in range(3):
                        with self.assertRaises(PpsError):
                            parse_recording(
                                recording, ParseOptions(output_dir=output), env=env
                            )

            self.assertEqual(list(output.glob("_work*")), [])

    def test_keep_work_preserves_this_runs_scratch_after_a_failure(self) -> None:
        from types import SimpleNamespace
        from unittest import mock

        env = Environment(
            ffmpeg=ToolStatus("ffmpeg", True, Path("/usr/bin/ffmpeg"), "stub"),
            ffprobe=ToolStatus("ffprobe", True, Path("/usr/bin/ffprobe"), "stub"),
            transcriber=ToolStatus("transcriber", False, None, "none"),
        )
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            recording = folder / "lecture.mp4"
            recording.write_bytes(b"stub")
            (folder / "lecture.srt").write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nHello.\n", encoding="utf-8"
            )
            output = folder / "out"

            with mock.patch(
                "podleparsesskewl.pipeline.probe_recording",
                return_value=SimpleNamespace(
                    duration_seconds=3.0,
                    width=640,
                    height=480,
                    has_audio=True,
                    has_video=True,
                ),
            ):
                with mock.patch(
                    "podleparsesskewl.pipeline.sample_signatures",
                    side_effect=PpsError("ffmpeg frame sampling failed"),
                ):
                    with self.assertRaises(PpsError):
                        parse_recording(
                            recording,
                            ParseOptions(output_dir=output, keep_work=True),
                            env=env,
                        )

            self.assertEqual(len(list(output.glob("_work*"))), 1)


class PipelineTests(unittest.TestCase):
    def test_parse_without_ffmpeg_is_a_clear_error(self) -> None:
        missing = ToolStatus("ffmpeg", False, None, "not installed")
        env = Environment(
            ffmpeg=missing,
            ffprobe=ToolStatus("ffprobe", False, None, "not installed"),
            transcriber=ToolStatus("transcriber", False, None, "not installed"),
        )
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            recording = folder / "lecture.mp4"
            recording.write_bytes(b"not a real video")
            with self.assertRaises(PpsError) as raised:
                parse_recording(recording, ParseOptions(output_dir=folder / "out"), env=env)
            self.assertIn("ffmpeg", str(raised.exception).lower())

    @unittest.skipUnless(_ffmpeg(), "ffmpeg not on PATH")
    def test_parse_synthetic_mp4_with_sidecar(self) -> None:
        ffmpeg = _ffmpeg()
        assert ffmpeg is not None
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            recording = _make_two_still_recording(folder, ffmpeg)
            output = folder / "out"
            result = parse_recording(
                recording,
                ParseOptions(
                    output_dir=output,
                    sample_fps=1.0,
                    min_hold_seconds=1.0,
                ),
            )
            self.assertTrue(result.document_path.is_file())
            self.assertTrue(result.html_path.is_file())
            self.assertGreaterEqual(len(result.document.stills), 2)
            self.assertEqual(len(result.document.sections), len(result.document.stills))
            first_image = output / result.document.stills[0].image
            self.assertTrue(first_image.is_file())
            self.assertGreater(first_image.stat().st_size, 0)
            html = result.html_path.read_text(encoding="utf-8")
            self.assertIn("Welcome to the first slide.", html)
            self.assertIn("second slide", html)
            rebuilt = render_html(result.document)
            self.assertIn("<hr>", rebuilt)
            self.assertEqual(result.document.source.transcript_source, "sidecar:srt:lecture.srt")
            self.assertEqual(list(output.glob("_work*")), [])
