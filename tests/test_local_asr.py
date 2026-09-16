"""Opt-in real-engine smoke test; PPS_TEST_MODEL_PATH must already exist locally."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(os.environ.get("PPS_TEST_MODEL_PATH"), "requires provisioned local ASR model")
class LocalAsrTests(unittest.TestCase):
    def test_offline_speech_audio_and_video(self) -> None:
        model = Path(os.environ["PPS_TEST_MODEL_PATH"])
        self.assertTrue(model.is_absolute() and model.is_dir())
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            speech = root / "speech.wav"
            subprocess.run([
                "espeak-ng", "-v", "en-us", "-s", "145", "-w", str(speech),
                "Welcome to this lecture. Today we study computer networks. "
                "A network connects computers so they can exchange information. "
                "Packets carry data from one computer to another. Thank you for listening.",
            ], check=True, capture_output=True)
            for suffix in ("mp3", "mp4"):
                with self.subTest(format=suffix):
                    media = root / f"lecture.{suffix}"
                    video = (["-f", "lavfi", "-i", "color=c=blue:s=320x240:r=25",
                              "-shortest"] if suffix == "mp4" else [])
                    subprocess.run(["ffmpeg", "-v", "error", "-i", str(speech),
                                    *video, str(media)], check=True, capture_output=True)
                    run = subprocess.run([
                        sys.executable, "-m", "podleparsesskewl", "transcribe", str(media),
                        "-o", str(root / suffix), "--whisper-model-path", str(model),
                        "--local-files-root", str(root / "cache"), "--device", "cpu",
                        "--jsonl-progress",
                    ], env={**os.environ, "HF_HUB_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1"},
                        capture_output=True, text=True, timeout=180)
                    self.assertEqual(run.returncode, 0, run.stderr)
                    events = [json.loads(line) for line in run.stdout.splitlines()]
                    self.assertEqual([e["phase"] for e in events if e["type"] == "progress"],
                                     ["checking", "processing", "validating", "done"])
                    result = events[-1]
                    self.assertTrue(result["provenance"]["offline"])
                    self.assertEqual(result["provenance"]["device_used"], "cpu")
                    self.assertTrue(result["provenance"]["transcript_source"].startswith("audio:faster-whisper:"))
                    for artifact in result["artifacts"].values():
                        self.assertTrue(Path(artifact).is_absolute() and Path(artifact).is_file())
                    document = json.loads(Path(result["artifacts"]["document"]).read_text())
                    cues = document["transcript"]["cues"]
                    text = " ".join(cue["text"] for cue in cues).lower()
                    for phrase in ("computer networks", "exchange information", "thank you for listening"):
                        self.assertIn(phrase, text)
                    report = Path(result["artifacts"]["transcript"]).read_text()
                    for cue in cues:
                        self.assertIn(cue["text"], report)
                        self.assertLess(cue["start_seconds"], cue["end_seconds"])
                        self.assertLessEqual(cue["end_seconds"], result["duration_seconds"] + 0.1)
                    self.assertEqual(result["counts"]["cues"], len(cues))
                    self.assertEqual(len(document["stills"]), 0 if suffix == "mp3" else 1)
                    self.assertEqual(list((root / suffix).glob("_work-*")), [])
