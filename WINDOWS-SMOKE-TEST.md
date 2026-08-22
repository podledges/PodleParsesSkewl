# Windows release smoke test

For an installed build, run these checks after installing `dist\PodleSkewl-Setup.exe`. The installer should create a Start Menu shortcut named `PodleSkewl`, and Windows Settings > Apps should offer an uninstall entry.

Run these checks from an extracted `PodleParsesSkewl-Windows` folder on a clean Windows 10/11 PC:

1. Confirm the folder contains `pps.exe`, `pps-gui.exe`, `PodleSkewl.exe`, this file, and `README.md`.
2. Double-click `PodleSkewl.exe`. Confirm the PodleSkewl window opens without a console window. The historical `pps-gui.exe` should also open the same GUI.
3. If ffmpeg is absent, confirm the GUI clearly reports the requirement and offers the download page.
4. Install a legal Windows ffmpeg build from <https://www.gyan.dev/ffmpeg/builds/>. Add its `bin` folder to PATH, or set `PODLEPARSESSKEWL_FFMPEG` and `PODLEPARSESSKEWL_FFPROBE` to the two `.exe` paths.
5. Run `pps.exe doctor`; confirm ffmpeg and ffprobe are `ok`.
6. Select a small MP4 with a same-name `.srt` sidecar in the GUI and create a review. Confirm `lecture.json`, `lecture.html`, `lecture.md`, and `stills\` are produced.
7. Run `pps.exe --version` and `pps.exe render path\to\lecture.json` to verify the CLI remains usable.
8. Confirm no `models`, lecture recordings, credentials, or other user data are present in the release folder, installer, or ZIP.
9. Uninstall from Windows Settings > Apps. Confirm the installed files and Start Menu shortcut are removed.

The release does not bundle ffmpeg, Whisper engines, or Whisper model files. Audio-only transcription requires a locally installed engine and model cache; caption sidecars work without one.
