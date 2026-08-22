from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from podleparsesskewl.archive import archive_inputs, unique_run_dir
from podleparsesskewl.errors import PpsError


class ArchiveTests(unittest.TestCase):
    def test_archive_moves_recording_and_sidecar_and_writes_a_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            recording = folder / "lecture.mp4"
            sidecar = folder / "lecture.srt"
            output = folder / "lecture.lecture"
            archive = folder / "archive"
            output.mkdir()
            recording.write_bytes(b"mp4")
            sidecar.write_text("captions", encoding="utf-8")
            (output / "lecture.json").write_text("{}", encoding="utf-8")

            result = archive_inputs(
                archive_dir=archive,
                recording=recording,
                sidecar=sidecar,
                output_dir=output,
                result_paths={"present": str(output / "lecture.present.html")},
                extra={"title": "Lecture", "stills": 2},
                when=datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc),
            )

            self.assertFalse(recording.exists())
            self.assertFalse(sidecar.exists())
            self.assertTrue((output / "lecture.json").is_file())
            self.assertTrue(result.run_dir.is_dir())
            self.assertTrue((result.run_dir / "lecture.mp4").is_file())
            self.assertTrue((result.run_dir / "lecture.srt").is_file())
            payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "ok")
            self.assertTrue(payload["input"]["original_recording"].endswith("lecture.mp4"))
            self.assertTrue(payload["input"]["archived_recording"].endswith("lecture.mp4"))
            self.assertEqual(payload["output"]["present"], str(output / "lecture.present.html"))
            self.assertEqual(payload["result"]["stills"], 2)

    def test_unique_run_dirs_never_reuse_an_existing_folder(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            archive = Path(raw)
            when = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
            first = unique_run_dir(archive, "lecture", when=when)
            first.mkdir()
            second = unique_run_dir(archive, "lecture", when=when)
            self.assertNotEqual(first, second)
            self.assertFalse(second.exists())

    def test_archive_does_not_reuse_an_existing_run_folder(self) -> None:
        from unittest import mock

        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            recording = folder / "lecture.mp4"
            recording.write_bytes(b"mp4")
            output = folder / "out"
            output.mkdir()
            existing = folder / "archive" / "keep-me"
            existing.mkdir(parents=True)
            kept = existing / "kept.txt"
            kept.write_text("keep", encoding="utf-8")

            with mock.patch("podleparsesskewl.archive.unique_run_dir", return_value=existing):
                with self.assertRaises(PpsError):
                    archive_inputs(
                        archive_dir=folder / "archive",
                        recording=recording,
                        sidecar=None,
                        output_dir=output,
                        result_paths={},
                    )
            self.assertTrue(recording.is_file())
            self.assertEqual(kept.read_text(encoding="utf-8"), "keep")

    def test_missing_recording_does_not_create_an_archive_folder(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            archive = folder / "archive"
            with self.assertRaises(PpsError):
                archive_inputs(
                    archive_dir=archive,
                    recording=folder / "missing.mp4",
                    sidecar=None,
                    output_dir=folder / "out",
                    result_paths={},
                )
            self.assertFalse(archive.exists())

    def test_sidecar_inside_output_is_left_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            recording = folder / "lecture.mp4"
            output = folder / "lecture.lecture"
            output.mkdir()
            recording.write_bytes(b"mp4")
            sidecar = output / "lecture.srt"
            sidecar.write_text("generated", encoding="utf-8")
            result = archive_inputs(
                archive_dir=folder / "archive",
                recording=recording,
                sidecar=sidecar,
                output_dir=output,
                result_paths={},
            )
            self.assertTrue(sidecar.is_file())
            self.assertFalse((result.run_dir / "lecture.srt").exists())
            self.assertTrue(any("output folder" in item for item in result.skipped))
