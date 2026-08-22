from pathlib import Path
import unittest


class WindowsPackagingTests(unittest.TestCase):
    def test_windows_build_inputs_are_committed_and_keep_media_external(self) -> None:
        root = Path(__file__).parents[1]
        script = (root / "scripts" / "build-windows.ps1").read_text(encoding="utf-8")
        spec = (root / "pps.spec").read_text(encoding="utf-8")
        gui_spec = (root / "pps-gui.spec").read_text(encoding="utf-8")
        gui = (root / "podleparsesskewl" / "gui.py").read_text(encoding="utf-8")
        readme = (root / "README.md").read_text(encoding="utf-8")
        smoke = (root / "WINDOWS-SMOKE-TEST.md").read_text(encoding="utf-8")

        self.assertIn("PyInstaller", script)
        self.assertIn("pps.spec", script)
        self.assertIn("pps-gui.spec", script)
        self.assertIn("Compress-Archive", script)
        self.assertIn('name="pps"', spec)
        self.assertIn('name="pps-gui"', gui_spec)
        self.assertIn("PodleParsesSkewl", gui)
        self.assertIn("does not include `ffmpeg` or `ffprobe`", readme)
        self.assertIn("PodleParsesSkewl-Windows.zip", readme + script)
        self.assertIn("pps-gui.exe", smoke)
        self.assertIn("WINDOWS-SMOKE-TEST.md", readme + script)
        self.assertNotIn("ffmpeg.exe", spec + gui_spec)
        self.assertNotIn("models", spec + gui_spec)


if __name__ == "__main__":
    unittest.main()
