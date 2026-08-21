from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from podleparsesskewl.deps import Environment, ToolStatus
from podleparsesskewl.media import probe_recording, sample_signatures
from podleparsesskewl.pipeline import ParseOptions, parse_recording
from podleparsesskewl.stills import DEFAULT_SAMPLE_HEIGHT, DEFAULT_SAMPLE_WIDTH, FrameSignature

FRAME_SIZE = DEFAULT_SAMPLE_WIDTH * DEFAULT_SAMPLE_HEIGHT


def _env() -> Environment:
    tool = ToolStatus("ffmpeg", True, Path("/usr/bin/ffmpeg"), "stub")
    probe = ToolStatus("ffprobe", True, Path("/usr/bin/ffprobe"), "stub")
    return Environment(
        ffmpeg=tool,
        ffprobe=probe,
        transcriber=ToolStatus("transcriber", False, None, "none"),
    )


def _probe_payload(duration: object) -> str:
    return json.dumps(
        {
            "format": {"duration": duration},
            "streams": [{"codec_type": "video", "width": 1920, "height": 1080}],
        }
    )


class ProbeTests(unittest.TestCase):
    def test_unusable_duration_reads_as_zero_instead_of_crashing(self) -> None:
        for duration in ("N/A", "", "not-a-number", None):
            with self.subTest(duration=duration):
                with mock.patch(
                    "podleparsesskewl.media._run",
                    return_value=SimpleNamespace(stdout=_probe_payload(duration), stderr=""),
                ):
                    probe = probe_recording(Path("lecture.mp4"), _env())
                self.assertEqual(probe.duration_seconds, 0.0)
                self.assertTrue(probe.has_video)

    def test_numeric_duration_is_read(self) -> None:
        with mock.patch(
            "podleparsesskewl.media._run",
            return_value=SimpleNamespace(stdout=_probe_payload("90.5"), stderr=""),
        ):
            probe = probe_recording(Path("lecture.mp4"), _env())
        self.assertEqual(probe.duration_seconds, 90.5)


class SampleTests(unittest.TestCase):
    def test_every_decoded_frame_is_sampled(self) -> None:
        frame_count = 120
        with tempfile.TemporaryDirectory() as raw:
            work = Path(raw) / "_work"

            def fake_run(command, label):
                work.mkdir(parents=True, exist_ok=True)
                (work / "signatures.gray").write_bytes(
                    b"".join(bytes([index % 256]) * FRAME_SIZE for index in range(frame_count))
                )
                return SimpleNamespace(stdout="", stderr="")

            with mock.patch("podleparsesskewl.media._run", side_effect=fake_run):
                frames = sample_signatures(Path("lecture.mp4"), work, _env(), fps=1.0)

        self.assertEqual(len(frames), frame_count)
        self.assertEqual(frames[-1].time_seconds, float(frame_count - 1))


class MissingDurationPipelineTests(unittest.TestCase):
    def test_stills_cover_the_recording_when_ffprobe_reports_no_duration(self) -> None:
        frames = [
            FrameSignature(
                time_seconds=float(index),
                width=DEFAULT_SAMPLE_WIDTH,
                height=DEFAULT_SAMPLE_HEIGHT,
                samples=bytes([0 if index < 60 else 255]) * FRAME_SIZE,
            )
            for index in range(120)
        ]
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            recording = folder / "lecture.mp4"
            recording.write_bytes(b"stub")
            sidecar = folder / "lecture.srt"
            sidecar.write_text(
                "1\n00:01:30,000 --> 00:01:35,000\nLate in the lecture.\n", encoding="utf-8"
            )
            output = folder / "out"

            def fake_still(_recording, _timestamp, dest: Path, _env):
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(b"\x89PNG")

            with mock.patch(
                "podleparsesskewl.pipeline.probe_recording",
                return_value=SimpleNamespace(
                    duration_seconds=0.0,
                    width=1920,
                    height=1080,
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
                        result = parse_recording(
                            recording,
                            ParseOptions(output_dir=output, sample_fps=1.0, min_hold_seconds=1.0),
                            env=_env(),
                        )

        document = result.document
        self.assertEqual(len(document.stills), 2)
        self.assertGreaterEqual(document.source.duration_seconds, 120.0)
        self.assertGreater(document.stills[-1].end_seconds, document.stills[-1].start_seconds)
        said = {section.still_id: section.said for section in document.sections}
        self.assertIn("Late in the lecture.", said["still-002"])
