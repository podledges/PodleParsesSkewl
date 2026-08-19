# PodleParsesSkewl

Standalone lecture review-reconstruction tool. Domain language lives in `CONTEXT.md`.

## Commands

```bash
python3 -m podleparsesskewl doctor
python3 -m podleparsesskewl parse path/to/lecture.mp4
python3 -m unittest discover -s tests -v
```

`doctor` is the source of truth for ffmpeg / transcriber / lecture-directory reachability. Setup and the Windows lecture directory are documented in `README.md`.

## Skills

`/ezLectures` renders an aesthetic HTML view from an existing `lecture.json`. Canonical skill: `.agents/skills/ezLectures/SKILL.md` (mirrored at `.grok/skills/ezLectures/SKILL.md`).

## Constraints

- One MP4 is one Lecture. The canonical result is `lecture.json`.
- Core path is local. Do not add a required cloud API.
- Do not treat "slide" as a second extracted object. The extracted visual is a Still.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
