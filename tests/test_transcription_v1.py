from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from podleparsesskewl.cli import main
from podleparsesskewl.deps import Environment, ToolStatus
from podleparsesskewl.document import Cue, LectureDocument, SourceInfo, Transcript
from podleparsesskewl.pipeline import ParseOptions, ParseResult, parse_recording
from podleparsesskewl.report import group_transcript, render_transcript_markdown
from podleparsesskewl.stills import FrameSignature, segment_stills


def _env() -> Environment:
    return Environment(
        ffmpeg=ToolStatus("ffmpeg", True, Path("/usr/bin/ffmpeg"), "stub"),
        ffprobe=ToolStatus("ffprobe", True, Path("/usr/bin/ffprobe"), "stub"),
        transcriber=ToolStatus("transcriber", False, None, "none"),
    )


class AudioOnlyTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg required for audio-only E2E")
    def test_mp3_with_sidecar_runs_end_to_end(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        assert ffmpeg is not None
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            recording = folder / "lecture.mp3"
            made = subprocess.run(
                [ffmpeg, "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "3", "-y", str(recording)],
                check=False,
                capture_output=True,
            )
            self.assertEqual(made.returncode, 0, made.stderr.decode(errors="replace"))
            (folder / "lecture.srt").write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nAudio only.\n",
                encoding="utf-8",
            )
            result = parse_recording(recording, ParseOptions(output_dir=folder / "out"))
            self.assertEqual(result.document.stills, ())
            self.assertEqual(result.document.sections, ())
            self.assertIn("Audio only.", result.transcript_path.read_text(encoding="utf-8"))

    def test_audio_only_writes_transcript_without_black_still(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            recording = folder / "lecture.mp3"
            recording.write_bytes(b"audio")
            (folder / "lecture.srt").write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nFirst.\n\n"
                "2\n00:00:04,000 --> 00:00:05,000\nSecond.\n",
                encoding="utf-8",
            )
            with mock.patch(
                "podleparsesskewl.pipeline.probe_recording",
                return_value=SimpleNamespace(
                    duration_seconds=5.0,
                    width=None,
                    height=None,
                    has_audio=True,
                    has_video=False,
                ),
            ):
                with mock.patch("podleparsesskewl.pipeline.sample_signatures") as sample:
                    with mock.patch("podleparsesskewl.pipeline.extract_still_png") as still:
                        result = parse_recording(
                            recording,
                            ParseOptions(output_dir=folder / "out"),
                            env=_env(),
                        )
            sample.assert_not_called()
            still.assert_not_called()
            self.assertEqual(result.document.stills, ())
            self.assertEqual(result.document.sections, ())
            text = result.transcript_path.read_text(encoding="utf-8")
            self.assertEqual(text.count("First."), 1)
            self.assertEqual(text.count("Second."), 1)
            self.assertIn("## 00:00:04", text)


class TranscriptGroupingTests(unittest.TestCase):
    def test_pause_visual_and_size_boundaries_preserve_each_cue_once(self) -> None:
        cues = (
            Cue(0.0, 1.0, "Um first."),
            Cue(1.2, 2.0, "Still first."),
            Cue(4.0, 5.0, "Second section."),
            Cue(5.1, 6.0, "After visual."),
        )
        groups = group_transcript(cues, pause_seconds=2.0, visual_boundaries=(5.05,))
        self.assertEqual([group.cue_indexes for group in groups], [(0, 1), (2,), (3,)])
        self.assertEqual(" ".join(group.text for group in groups).count("first."), 2)

    def test_transcript_report_is_cue_led_and_faithful(self) -> None:
        cues = (Cue(3601, 3602, "Um `x` = 42, 42."),)
        document = LectureDocument(
            "Audio",
            SourceInfo("audio.mp3", 3602, "sidecar:srt:audio.srt"),
            (),
            Transcript(cues, "sidecar:srt:audio.srt"),
            (),
        )
        text = render_transcript_markdown(document)
        self.assertIn("## 01:00:01", text)
        self.assertEqual(text.count("Um `x` = 42, 42."), 1)


class LookbackTests(unittest.TestCase):
    def test_held_swap_is_coalesced_and_return_to_prior_state_is_kept(self) -> None:
        frames = [
            FrameSignature(float(t), 16, 16, bytes([0 if t < 5 or t >= 10 else 255]) * 256)
            for t in range(40)
        ]
        intervals = segment_stills(
            frames,
            duration_seconds=40,
            min_hold_seconds=1,
            lookback_seconds=30,
        )
        self.assertEqual([interval.start_seconds for interval in intervals], [0.0, 5.0, 10.0])

    def test_thirty_second_lookback_does_not_use_last_accepted_anchor(self) -> None:
        frames = [FrameSignature(float(t), 16, 16, bytes([t // 2]) * 256) for t in range(101)]
        anchored = segment_stills(frames, duration_seconds=101)
        lookback = segment_stills(frames, duration_seconds=101, lookback_seconds=30)
        self.assertGreater(len(anchored), 1)
        self.assertEqual(len(lookback), 1)


class AgentContractTests(unittest.TestCase):
    def test_machine_result_returns_paths_not_transcript_body(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            recording = folder / "lecture.mp3"
            recording.write_bytes(b"audio")
            output = folder / "result"
            output.mkdir()
            artifacts = {
                name: output / filename
                for name, filename in {
                    "document": "lecture.json",
                    "transcript": "transcript.md",
                    "html": "lecture.html",
                    "markdown": "lecture.md",
                }.items()
            }
            for path in artifacts.values():
                path.write_text("SECRET FULL TRANSCRIPT BODY", encoding="utf-8")
            document = LectureDocument(
                "Audio",
                SourceInfo(str(recording), 10, "sidecar:srt:lecture.srt"),
                (),
                Transcript((Cue(0, 1, "short excerpt"),), "sidecar:srt:lecture.srt"),
                (),
            )
            result = ParseResult(
                document,
                artifacts["document"],
                artifacts["html"],
                artifacts["markdown"],
            )
            stdout = io.StringIO()
            with mock.patch("podleparsesskewl.cli.parse_recording", return_value=result):
                with contextlib.redirect_stdout(stdout):
                    code = main(["transcribe", str(recording), "-o", str(output)])
            payload = json.loads(stdout.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(payload["artifacts"]["transcript"], str(artifacts["transcript"]))
            self.assertNotIn("SECRET FULL TRANSCRIPT BODY", stdout.getvalue())
            self.assertLessEqual(len(payload["index"]), 40)

    @unittest.skipIf(shutil.which("node") is None or os.name == "nt", "POSIX Node cancellation regression")
    def test_pi_bridge_kills_a_spawned_descendant(self) -> None:
        script = r'''
import { spawn } from "node:child_process";
import { stopTree } from "./pi/extensions/process-tree.ts";
const parent = spawn(process.execPath, ["-e", `
  const { spawn } = require("node:child_process");
  const child = spawn(process.execPath, ["-e", "process.on('SIGTERM', () => {}); setInterval(() => {}, 1000)"]);
  console.log(child.pid);
  setInterval(() => {}, 1000);
`], { detached: true, stdio: ["ignore", "pipe", "ignore"] });
const pid = Number(await new Promise(resolve => parent.stdout.once("data", chunk => resolve(chunk.toString().trim()))));
await stopTree(parent);
await new Promise(resolve => setTimeout(resolve, 100));
try { process.kill(pid, 0); process.exit(2); } catch { process.exit(0); }
'''
        completed = subprocess.run(
            [shutil.which("node"), "--input-type=module", "-e", script],
            cwd=Path(__file__).parent.parent,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        source = Path("pi/extensions/transcribe.ts").read_text(encoding="utf-8")
        self.assertIn('pi.on("session_shutdown"', source)
        self.assertIn("signal?.addEventListener", source)


if __name__ == "__main__":
    unittest.main()
