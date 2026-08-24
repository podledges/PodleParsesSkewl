# PodleParsesSkewl

Standalone lecture review-reconstruction tool. Domain language lives in `CONTEXT.md`.

## Commands

```bash
python3 -m podleparsesskewl doctor
python3 -m podleparsesskewl parse path/to/lecture.mp4
nix-shell --run 'python3 -m unittest discover -s tests -v'
```

`doctor` is the source of truth for ffmpeg / transcriber / lecture-directory reachability. Setup and the Windows lecture directory are documented in `README.md`.

CI (GitHub Actions) is the remote automated check machine. Do not treat CI green as the real MP4 media test. Run the suite locally with ffmpeg from `shell.nix` so the synthetic MP4 parse actually executes.

## Skills

Canonical definitions live under `.agents/skills/<skill>/SKILL.md`. Harness entries in `.claude/skills/` and `.grok/skills/` are discovery pointers, never copies.

- `/parse-skewl` runs this repo's parser on one local MP4.
- `/present` writes teaching notes (`lecture.present.html`) from an existing `lecture.json`. Sibling of `/ezLectures`; it teaches, it does not replay Said verbatim.
- `/parse-skewl-notes` runs parse, `/present`, and optional input archive.
- `/ezLectures` renders a faithful aesthetic HTML view from an existing `lecture.json`.

## Constraints

- One MP4 is one Lecture. The canonical result is `lecture.json`.
- Core path is local. Do not add a required cloud API.
- Do not treat "slide" as a second extracted object. The extracted visual is a Still.
- v1 still detection uses `DEFAULT_CHANGE_RATIO = 0.15` so a text-heavy full-slide swap splits and a typical one-bullet progressive build stays merged. v2 may split a held build only when the added content is large enough and/or held long enough; those thresholds are not designed yet. See `podleparsesskewl/stills.py`.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
