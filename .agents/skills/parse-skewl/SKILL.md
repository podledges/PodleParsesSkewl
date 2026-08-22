---
name: parse-skewl
description: >
  Parse a lecture MP4 into a PodleParsesSkewl Lecture Document with this
  repo's local CLI. Use when the user runs /parse-skewl, asks to parse a
  lecture recording, or wants lecture.json / stills / plain HTML from an MP4.
---

# /parse-skewl

Turn one local Recording (MP4) into a Lecture Document using this project's parser. Do not reimplement ffmpeg, still detection, or transcription.

## Completion

Done when `pps parse` (or `python3 -m podleparsesskewl parse`) has written `lecture.json`, `lecture.html`, `lecture.md`, and `stills/` for the named Recording, and you have reported those paths. Do not archive the input. Do not write teaching notes (that is `/present` or `/parse-skewl-notes`).

## Steps

1. Work from the PodleParsesSkewl repository root. If the environment is unknown, run `python3 -m podleparsesskewl doctor` and fix ffmpeg / sidecar / lecture-directory issues it names.
2. Resolve the Recording: an explicit MP4 path, or `--latest` when the lecture directory is accessible. Lecture files stay on local disk. Do not upload them.
3. Resolve the output folder: honor an explicit path; otherwise let the CLI use `--default-output-dir` / config `output_dir` / `PODLEPARSESSKEWL_OUTPUT_DIR`, which writes `<parent>/<stem>.lecture`. With none of those, the default is `<recording>.lecture/` next to the file.
4. Run the shared command, not a private rewrite:

   ```bash
   python3 -m podleparsesskewl parse path/to/lecture.mp4
   python3 -m podleparsesskewl parse path/to/lecture.mp4 -o path/to/out
   python3 -m podleparsesskewl parse path/to/lecture.mp4 --transcript path/to/lecture.srt --offline-transcription
   ```

5. Report Document, HTML, Markdown, Still count, and cue count from the command output.

If you are a manager agent, dispatch an implementation subagent with the resolved paths and this command; do not parse frames yourself.

## Boundaries

- Core path is local. Do not add a cloud API. Do not send lecture audio, stills, or transcripts off-machine.
- Whisper models and caches stay in `./models`, `--local-files-root`, or `--whisper-model-path`. Prefer `--offline-transcription` once a model is cached. Never commit or bundle models, lecture files, or user caches.
- Domain language lives in `CONTEXT.md`. The extracted visual is a Still, not a slide object.
- `/ezLectures` is a later HTML dressing step on an existing Document. Do not run it from this skill.
