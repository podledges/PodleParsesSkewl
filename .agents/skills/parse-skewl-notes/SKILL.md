---
name: parse-skewl-notes
description: >
  Parse a lecture MP4 with PodleParsesSkewl and write both views in one
  headless run. Use when the user runs /parse-skewl-notes, wants parse plus
  notes, or asks to process a recording all the way to study notes. Prefer
  this over chaining /parse-skewl and /present yourself.
---

# /parse-skewl-notes

Parse one local Recording headlessly. `pps notes` writes `lecture.review.html`, one page with the teaching view and the faithful Still-plus-Said view. Archive is off unless `--archive` is passed or `archive_after_notes` is true.

## Completion

Done when `pps notes` has exited 0 and stdout is one JSON object whose `open` field is `lecture.review.html`. Report that path. The Recording stays where it was unless the JSON `archive` field is set. On failure, the Recording stays at its original path unless the command itself printed a partial-archive error. Pass `--pick` only when the person asked for a file picker. Do not prompt.

## Steps

1. Work from the PodleParsesSkewl repository root. Resolve the Recording first. A bad selection is reported even when ffmpeg or a transcription engine is missing. `pps notes` then stops before parse if ffmpeg or ffprobe is missing, or if a transcription engine is missing and Said will be transcribed. A `--transcript` or an adjacent sidecar supplies Said without the engine, and a Recording with no audio track is not a missing-engine failure. The stderr text is the setup and the exact command to retry. An explicit Recording path and `--find` with an explicit `--in` folder are not blocked because the configured lecture directory is unreachable. `--latest` still refuses an inaccessible lecture directory.
2. Resolve the Recording by a path, `--latest`, `--find` with `--in`, or `--pick` when the person asked for a file picker. `list`, `--latest`, and `--find` search recursively, including course subfolders. Exactly one `--find` match proceeds. Zero or many is a non-zero exit that lists the full paths; report those paths and stop. Lecture files stay local. Do not upload them.
3. Run the shared command. Quote paths that contain spaces:

   ```bash
   python3 -m podleparsesskewl notes path/to/lecture.mp4
   python3 -m podleparsesskewl notes --find Week5 --in "/mnt/c/Users/ayden/Documents/SCHOOL/NUS Y3S1"
   python3 -m podleparsesskewl notes path/to/lecture.mp4 --archive --archive-dir path/to/archive
   ```

4. Open the path in the JSON `open` field. That page already carries both views. Follow `.agents/skills/present/SKILL.md` only to tighten the teaching half of `lecture.review.html` in place. When the run was `pps notes`, edit that teaching half in place and do not retarget standalone `/present`, which still writes `lecture.present.html`. Mental models, applications only when Said supplies them, local diagrams only where the Shown is not enough. Keep image `src` relative. Do not invent Said. Do not rewrite the faithful half.
5. Do not move files yourself. `--archive` moves the Recording into a unique run folder after the review page exists. `--no-archive` leaves it in place even when config would archive. Never overwrite an existing archive folder.

If you are a manager agent, dispatch an implementation subagent with the resolved paths and the `pps notes` command, then a second pass that follows `/present` on the review page's teaching half.

## Boundaries

- Same local-only rules as `/parse-skewl`: no cloud API, no bundled models, no committed lecture files.
- `--pick` is an explicit notes flag. Pass it only when the person asked for a file picker. A failed or ambiguous search lists paths and stops.
- Move happens only after `lecture.review.html` exists, and only when archive was requested. If parse or present fails, leave the input where it is.
- `pps present` and `pps render` still write one view alone. Do not use them instead of `notes` when the captain asked for the run.
