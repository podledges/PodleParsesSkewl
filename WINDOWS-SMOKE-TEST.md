# Windows release smoke test

For an installed build, run these checks after installing `dist\PodleSkewl-Setup.exe`. The installer should create a Start Menu shortcut named `PodleSkewl`, and Windows Settings > Apps should offer an uninstall entry.

Run these checks from an extracted `PodleParsesSkewl-Windows` folder on a clean Windows 10/11 PC:

1. Confirm the folder contains `pps.exe`, `pps-gui.exe`, `PodleSkewl.exe`, this file, and `README.md`.
2. Double-click `PodleSkewl.exe`. Confirm the PodleSkewl window opens without a console window. The historical `pps-gui.exe` should also open the same GUI.
3. If ffmpeg is absent, confirm the GUI clearly reports the requirement and offers the download page.
4. Install a legal Windows ffmpeg build from <https://www.gyan.dev/ffmpeg/builds/>. Add its `bin` folder to PATH, or set `PODLEPARSESSKEWL_FFMPEG` and `PODLEPARSESSKEWL_FFPROBE` to the two `.exe` paths.
5. Run `pps.exe doctor`; confirm ffmpeg and ffprobe are `ok`.
6. Select a small MP4 with a same-name `.srt` sidecar in the GUI. Confirm the output folder can be left empty (default next to the recording, or from config) or chosen with Browse. Use **Parse** and confirm `lecture.json`, `lecture.html`, `lecture.md`, and `stills\` are produced. The recording should still be in its original folder.
7. Use **Parse + Notes** on another small MP4 (or the same file if you copy it first). Confirm `lecture.present.html` is written next to the Document. If "move the input into the archive" is checked, the MP4 and sidecar should be gone from the original folder and present in a unique timestamped folder under the archive path, with `archive-manifest.json` naming the original and new locations. Unchecking that box, or `pps.exe notes file.mp4 --no-archive`, must leave the input in place.
8. Run `pps.exe --version`, `pps.exe present path\to\lecture.json`, and `pps.exe render path\to\lecture.json` to verify the CLI remains usable.
9. Confirm no `models`, lecture recordings, credentials, or other user data are present in the release folder, installer, or ZIP.
10. Uninstall from Windows Settings > Apps. Confirm the installed files and Start Menu shortcut are removed.

The release does not bundle ffmpeg, Whisper engines, or Whisper model files. Audio-only transcription requires a locally installed engine and model cache; caption sidecars work without one.
