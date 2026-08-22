from pathlib import Path
import unittest


class WindowsPackagingTests(unittest.TestCase):
    def test_windows_build_inputs_are_committed_and_keep_media_external(self) -> None:
        root = Path(__file__).parents[1]
        script = (root / "scripts" / "build-windows.ps1").read_text(encoding="utf-8")
        spec = (root / "pps.spec").read_text(encoding="utf-8")
        gui_spec = (root / "pps-gui.spec").read_text(encoding="utf-8")
        installed_gui_spec = (root / "PodleSkewl.spec").read_text(encoding="utf-8")
        installer = (root / "installer" / "PodleSkewl.iss").read_text(encoding="utf-8")
        gui = (root / "podleparsesskewl" / "gui.py").read_text(encoding="utf-8")
        readme = (root / "README.md").read_text(encoding="utf-8")
        smoke = (root / "WINDOWS-SMOKE-TEST.md").read_text(encoding="utf-8")

        self.assertIn("PyInstaller", script)
        self.assertIn("pps.spec", script)
        self.assertIn("pps-gui.spec", script)
        self.assertIn("PodleSkewl.spec", script)
        self.assertIn("Compress-Archive", script)
        self.assertIn('name="pps"', spec)
        self.assertIn('name="pps-gui"', gui_spec)
        self.assertIn('name="PodleSkewl"', installed_gui_spec)
        self.assertIn("PodleSkewl-Setup", installer)
        self.assertIn("{group}\\PodleSkewl", installer)
        self.assertIn("Source: \"..\\dist\\PodleSkewl.exe\"", installer)
        self.assertIn("Source: \"..\\dist\\pps.exe\"", installer)
        self.assertIn("PodleSkewl", gui)
        self.assertIn("do not include `ffmpeg` or `ffprobe`", readme)
        self.assertIn("PodleParsesSkewl-Windows.zip", readme + script)
        self.assertIn("PodleSkewl-Setup.exe", readme + script + smoke)
        self.assertIn("pps-gui.exe", smoke)
        self.assertIn("PodleSkewl.exe", smoke)
        self.assertIn("WINDOWS-SMOKE-TEST.md", readme + script)
        self.assertNotIn("ffmpeg.exe", spec + gui_spec + installed_gui_spec + installer)
        self.assertNotIn("models", spec + gui_spec + installed_gui_spec + installer)


if __name__ == "__main__":
    unittest.main()
