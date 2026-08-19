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

    def test_a_plain_relative_image_is_copied(self) -> None:
        from podleparsesskewl.pipeline import copy_still_images

        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            source = folder / "lecture"
            (source / "stills").mkdir(parents=True)
            (source / "stills" / "still-001.png").write_bytes(b"\x89PNG")
            target = folder / "out"
            target.mkdir()
            missing = copy_still_images(
                self._document("stills/still-001.png"), source, target
            )
            self.assertEqual(missing, [])
            self.assertTrue((target / "stills" / "still-001.png").is_file())


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
                    change_ratio=0.30,
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
            self.assertFalse((output / "_work").exists())
