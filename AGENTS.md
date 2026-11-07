# PodleParsesSkewl

Standalone lecture review-reconstruction tool. Domain language lives in `CONTEXT.md`.

## Commands

```bash
python3 -m podleparsesskewl doctor
python3 -m podleparsesskewl parse path/to/lecture.mp4
python3 -m podleparsesskewl transcribe path/to/lecture.mp4 --local-files-root /absolute/model/cache
python3 -m podleparsesskewl modules sync
python3 -m podleparsesskewl modules show 4704
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
- The Pi package registers `/transcribe`, `pps_transcribe`, and `/skill:transcribe`; setup and absolute runtime/model environment variables are in `README.md`.
- `/module` syncs the private modules clone, resolves a module mention, shows or edits its knowledge tree, and adds modules or aliases. Canonical file `.agents/skills/module/SKILL.md`.

## Modules

A Module is one taught course (`EE4704 - Image Processing and Analysis`). Modules live in the private PodleModules repo, cloned at `modules/` (ignored here; never commit anything under it to this repo). Each module is a folder `modules/<CODE> - <Short>/` with `module.json`, `knowledge-tree.md`, optional `README.md`, own work in `work/`, and received course material in the ignored `material/`. Layout, naming, tree format, sync and machine setup: `docs/modules.md`. Agent protocol: `/module`.

Before module work, run `python3 -m podleparsesskewl modules sync` (pull with rebase and autostash, regenerate the table, commit, push; keeps both PCs current) and read `modules/MODULES.md`, the generated module table with aliases. A code, bare number or alias in that table resolves in place; anything else (`img analysis`, `the image module`) runs `pps modules resolve "<mention>"`, and on `suggest`, `ambiguous` or `unknown` ask one short question, then persist the answer with `pps modules alias` or `pps modules add`.

"Show the 4704 knowledge tree" (also plan, map, list, prerequisites) means `pps modules show 4704`: print the file, do not summarize it. Run `modules sync` again after editing a tree. If `modules/` is missing on this machine, run `pps modules init <private repo url>` once.

## GUI

Windows launcher: `podleparsesskewl/gui.py`. Next-step issue plan and open captain choices: `docs/gui-implementation-plan.md`.

## Constraints

- Recording/Lecture cardinality and the canonical Document are defined in `CONTEXT.md`.
- Core path is local. Do not add a required cloud API.
- Do not treat "slide" as a second extracted object. The extracted visual is a Still.
- v1 still detection uses `DEFAULT_CHANGE_RATIO = 0.15` so a text-heavy full-slide swap splits and a typical one-bullet progressive build stays merged. v2 may split a held build only when the added content is large enough and/or held long enough; those thresholds are not designed yet. See `podleparsesskewl/stills.py`.
- Nothing under `modules/` is ever committed to this repo; it is a clone of the private modules repo. Received course material (textbooks, slides, recordings, parsed lectures) is never committed or uploaded anywhere, including that private repo; it stays in each module's ignored `material/` and `lectures/`.
- Module files go in that module's folder; private records that belong to no module go in `modules/_project/`; `docs/` is only for how things work.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
