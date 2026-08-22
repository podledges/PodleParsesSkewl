from pathlib import Path
import unittest


class WindowsPackagingTests(unittest.TestCase):
    def test_windows_build_inputs_are_committed_and_keep_media_external(self) -> None:
        root = Path(__file__).parents[1]
        script = (root / "scripts" / "build-windows.ps1").read_text(encoding="utf-8")
        spec = (root / "pps.spec").read_text(encoding="utf-8")
        readme = (root / "README.md").read_text(encoding="utf-8")

        self.assertIn("PyInstaller", script)
        self.assertIn("pps.spec", script)
        self.assertIn('name="pps"', spec)
        self.assertIn("does not include `ffmpeg` or `ffprobe`", readme)
        self.assertIn(".\\dist\\pps.exe --version", readme)
        self.assertNotIn("ffmpeg.exe", spec)
        self.assertNotIn("models", spec)


if __name__ == "__main__":
    unittest.main()
