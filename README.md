# PodleParsesSkewl

Review reconstruction for lecture recordings. One MP4 in; a structured Lecture Document out that pairs **what was said** with **what was shown**.

The program is a standalone CLI. Sidecar-based parsing is fully offline. Audio transcription runs locally; the default named Whisper model may be downloaded once, then reused from local disk. A project skill, `/ezLectures`, can turn the same Document into a more aesthetic HTML view.

## What you get

One Recording (an MP4) is one Lecture. The program writes a folder:

```
lecture.lecture/
  lecture.json      # canonical structured Document
  lecture.html      # plain program view
  lecture.md        # same pairing in Markdown
  stills/
    still-001.png
    still-002.png
    ...
```

The plain view is: Still image, a line separator, then the transcript that belongs to that Still. Repeat, with a separator between Stills. A Still nobody spoke over keeps that separator but shows no empty transcript block.

A **Still** is a visually stable interval plus the representative image taken from it. A slide change is the common case. A small webcam bubble is tolerated and should not split a stable slide.

## Setup

### Required

- Python 3.11+
- [ffmpeg](https://ffmpeg.org/) (includes `ffprobe`) on `PATH`

```bash
# Debian / Ubuntu
sudo apt-get install ffmpeg

# macOS
brew install ffmpeg

# Nix
nix-shell   # uses the repo's shell.nix
```

No Python packages are required for the core path. The repo has zero runtime dependencies.

```bash
git clone https://github.com/podledges/PodleParsesSkewl.git
cd PodleParsesSkewl
python3 -m podleparsesskewl doctor
```

Optional install, if you want the `pps` command on your PATH:

```bash
python3 -m pip install -e .
pps doctor
```

### Windows executable release

Maintainers can build the console executable on a Windows machine with Python 3.11+ and PowerShell:

```powershell
.\scripts\build-windows.ps1
```

The script creates a local build environment, installs the project and PyInstaller, and writes a Windows installer at `dist\PodleSkewl-Setup.exe`, plus the copy-ready folder and ZIP at `dist\PodleParsesSkewl-Windows`. The folder contains `pps.exe` (CLI), the historical `pps-gui.exe`, and `PodleSkewl.exe` (the installer GUI), plus release notes. The installer creates a Start Menu shortcut, optionally a desktop shortcut, and an entry in Windows Apps for clean uninstall. Extract the ZIP anywhere and double-click `pps-gui.exe`, or use the CLI directly:

```powershell
.\dist\PodleParsesSkewl-Windows\pps.exe --version
.\dist\PodleParsesSkewl-Windows\pps-gui.exe
```

Run [WINDOWS-SMOKE-TEST.md](WINDOWS-SMOKE-TEST.md) against the extracted artifact before sharing it.

Build on Windows - PyInstaller does not cross-compile a Windows executable from Linux or macOS. The installer is built with Inno Setup 6, which must also be installed on the Windows build machine and available as `ISCC.exe` on `PATH`. To build only the folder/ZIP when Inno Setup is unavailable, use `.\scripts\build-windows.ps1 -SkipInstaller`. The executable and installer do not include `ffmpeg` or `ffprobe`; install a legal Windows ffmpeg package separately and put its `bin` directory on `PATH` (or set `PODLEPARSESSKEWL_FFMPEG` and `PODLEPARSESSKEWL_FFPROBE`). Run `.\dist\pps.exe doctor` to verify the setup. Whisper model files and lecture data are also intentionally external and remain in local paths such as `models\` and the configured lecture directory.

The release build includes the core CLI and Podle-themed GUI, and supports caption sidecars without additional Python installation. Audio transcription still requires a separately installed local transcription engine and its model cache; it is not bundled by this build.

### Optional local transcription

If the MP4 has no caption sidecar, install a local engine:

```bash
python3 -m pip install -e ".[transcribe]"   # faster-whisper
```

The first audio run with the default named model (`base`) may download the model into `./models`. That cache is just model files kept on local disk, so later runs - including batch or multiple-file runs - reuse them and do not download again. Caching does not make transcription slower except for normal disk access. Lecture files are never uploaded.

Model recommendations:

- `tiny`: fastest and smallest, least accurate.
- `base`: default balance for quick review reconstruction.
- `small`: better accuracy when you can wait longer.
- `medium` or larger: best local accuracy, but much slower and larger.

Use `--whisper-model <tiny|base|small|medium|large...>` to choose a named model, `--local-files-root <path>` to choose where downloaded model files are stored, `--offline-transcription` to require cache-only operation, or `--whisper-model-path <path>` to use an explicit existing local model file or directory. After a model is present in `./models` or your chosen local-files root, `--offline-transcription` performs audio transcription without network access.

`./models` is the project-visible model location. It is ignored by git and can hold real model files, a symlink to another model cache, or symlinked entries that point at model files or directories you already have elsewhere. For example, once you find an existing transcription-model folder, you can keep this project local-first while reusing it with `ln -s /path/to/transcription-model ./models` or by linking selected files inside `./models`. If you do not want symlinks, pass the existing location directly with `--local-files-root /path/to/transcription-model` or use `--whisper-model-path /path/to/model-file-or-directory`.

## Usage

```bash
# check tools and the configured lecture directory
python3 -m podleparsesskewl doctor

# parse one Recording
python3 -m podleparsesskewl parse path/to/lecture.mp4

# choose output and an existing transcript
python3 -m podleparsesskewl parse path/to/lecture.mp4 \
  -o ./out/lecture \
  --transcript path/to/lecture.srt

# transcribe audio with cached/local model files only
python3 -m podleparsesskewl parse path/to/lecture.mp4 \
  --offline-transcription \
  --local-files-root ./models

# rebuild the plain HTML from an existing Document
python3 -m podleparsesskewl render ./out/lecture/lecture.json

# render into a different folder (the Still images are copied along)
python3 -m podleparsesskewl render ./out/lecture/lecture.json -o ./elsewhere
```

`render -o` copies `lecture.json` and every referenced Still image into the target folder, so the relative `stills/...` links in the rendered HTML keep resolving. Without `-o` the views are rebuilt beside the Document and the canonical `lecture.json` is left untouched.

End-to-end: `parse` writes `lecture.json` (canonical) and `lecture.html` (plain view) in one command.

### Transcripts

The program looks next to the MP4 for a transcript sidecar with the same stem, such as `lecture.srt`, `lecture.vtt`, or `lecture.json` beside `lecture.mp4`. If one is present, it is used and audio is not transcribed. If none is present, a local engine is required.

A JSON sidecar must be a list of cues, or an object holding a `cues` or `segments` list, where each cue has `start`/`end` (seconds or `HH:MM:SS.mmm`) and `text`.

A sidecar always wins over audio, so an empty or unreadable one stops the run instead of quietly producing a Lecture with no Said. If a capture tool left a stub `lecture.srt` behind and you want the audio transcribed, delete the stub and run `parse` again.

Audio transcription is held to the same bar: if the local engine finds no speech at all - a silent or very quiet Recording - `parse` says so rather than writing a Lecture whose every Said is blank.

A `lecture.json` Lecture Document sits at exactly the path a JSON sidecar would, so the program recognizes its own canonical output and never feeds it back in as a transcript. If a Recording has no audio track and no sidecar, `parse` says so instead of asking ffmpeg for audio that is not there.

### v1 recording layouts

In scope: clean full-frame slides, and screen-share-dominant recordings. A small webcam bubble may be ignored. Messy classroom / Zoom mosaics are out of scope.

## Windows lecture directory

The default lecture directory is:

```
C:\Users\ayden\Videos\Lectures
```

On the captain's Windows machine, `pps list` and `pps parse --latest` use that folder when it exists.

On any other machine (including this Linux worktree) that path is not visible. That is expected:

1. Pass an MP4 path to `parse` directly, or
2. Set `PODLEPARSESSKEWL_LECTURES_DIR` to a local folder, or
3. Copy `podleparsesskewl.toml.example` to `podleparsesskewl.toml` and point `lectures_dir` at a reachable path.

Your own `podleparsesskewl.toml` stays local; it is git-ignored. Only the example file is committed.

Agents working on a machine that cannot see the Windows folder should retrieve the MP4s from `C:\Users\ayden\Videos\Lectures` onto the machine, then run `parse`.

### Where the lecture directory comes from

Explicit settings beat ambient ones, in this order:

1. `--lectures-dir <path>`
2. `--config <file>` (an explicitly named config file wins over the environment)
3. `PODLEPARSESSKEWL_LECTURES_DIR`
4. A discovered `podleparsesskewl.toml` (working directory, then `~/.config/podleparsesskewl/`)
5. The default `C:\Users\ayden\Videos\Lectures`

`pps doctor` prints the resolved path and which of these it came from.

### WSL

Under WSL, a Windows lecture directory is translated automatically, so `C:\Users\ayden\Videos\Lectures` is used as `/mnt/c/Users/ayden/Videos/Lectures`. That applies to the default, the config file, the environment variable, and the flag:

```bash
python3 -m podleparsesskewl list          # already reads /mnt/c/Users/ayden/Videos/Lectures
python3 -m podleparsesskewl doctor        # shows the translation it applied
```

Setting the WSL path directly still works:

```bash
export PODLEPARSESSKEWL_LECTURES_DIR=/mnt/c/Users/ayden/Videos/Lectures
```

You can also set `PODLEPARSESSKEWL_FFMPEG` / `PODLEPARSESSKEWL_FFPROBE` if those binaries are not on `PATH`. Under WSL these accept a Windows path too (`C:\ffmpeg\bin\ffmpeg.exe` is tried as `/mnt/c/ffmpeg/bin/ffmpeg.exe`). If an override does not point at a file, `doctor` names the variable rather than reporting the tool as generically missing.

## Aesthetic HTML

`/ezLectures` is an agent skill. It reads `lecture.json` and writes a dressed HTML view. It does not re-extract Stills or re-transcribe audio.

The canonical skill file is `.agents/skills/ezLectures/SKILL.md` - edit that one. `.claude/skills/ezLectures/SKILL.md` and `.grok/skills/ezLectures/SKILL.md` exist only so Claude Code and Grok can discover `/ezLectures`; both point back at the canonical file instead of copying it.

## Tests

CI is GitHub Actions: a remote machine that installs ffmpeg and runs `python -m unittest` on every push and pull request. That is the automated check. It is not the only real media test.

The MP4 end-to-end parse (synthetic two-Still recording) must also be run locally, with ffmpeg/ffprobe actually present. On this NixOS/WSL repo that means the project `shell.nix`, not "CI was green so the media path is fine":

```bash
# preferred on Nix: ffmpeg from shell.nix, including the MP4 E2E
nix-shell --run 'python3 -m unittest discover -s tests -v'

# if ffmpeg is already on PATH
python3 -m unittest discover -s tests -v
```

Core tests use deterministic fixtures (captions, synthetic frame signatures, Document rendering). The MP4 E2E builds a tiny two-Still file and parses it; it is skipped only when ffmpeg is missing from that process, which is a local-setup gap, not a substitute for running the media test.

## Domain language

See [CONTEXT.md](CONTEXT.md).
