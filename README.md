# PodleParsesSkewl

Review reconstruction for lecture recordings. One MP4 in; a structured Lecture Document out that pairs **what was said** with **what was shown**.

The program is a standalone CLI. It does not call the network. A project skill, `/ezLectures`, can turn the same Document into a more aesthetic HTML view.

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

### Optional local transcription

If the MP4 has no caption sidecar, install a local engine:

```bash
python3 -m pip install -e ".[transcribe]"   # faster-whisper
```

The first audio run downloads a local Whisper model. Nothing is uploaded.

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

# rebuild the plain HTML from an existing Document
python3 -m podleparsesskewl render ./out/lecture/lecture.json

# render into a different folder (the Still images are copied along)
python3 -m podleparsesskewl render ./out/lecture/lecture.json -o ./elsewhere
```

`render -o` copies `lecture.json` and every referenced Still image into the target folder, so the relative `stills/...` links in the rendered HTML keep resolving. Without `-o` the views are rebuilt beside the Document and the canonical `lecture.json` is left untouched.

End-to-end: `parse` writes `lecture.json` (canonical) and `lecture.html` (plain view) in one command.

### Transcripts

The program looks next to the MP4 for `lecture.srt`, `lecture.vtt`, or `lecture.json`. If one is present, it is used and audio is not transcribed. If none is present, a local engine is required.

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

```bash
python3 -m unittest discover -s tests -v
```

Core tests use deterministic fixtures (captions, synthetic frame signatures, Document rendering). If `ffmpeg` is on `PATH`, an end-to-end test builds a tiny two-Still MP4 and parses it.

## Domain language

See [CONTEXT.md](CONTEXT.md).
