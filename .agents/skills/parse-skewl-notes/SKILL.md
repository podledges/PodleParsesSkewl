---
name: parse-skewl-notes
description: >
  Parse a lecture MP4 with PodleParsesSkewl and write teaching notes in one
  flow. Use when the user runs /parse-skewl-notes, wants parse plus notes,
  or asks to process a recording all the way to study notes. Prefer this
  over chaining /parse-skewl and /present yourself.
---

# /parse-skewl-notes

Parse one local Recording, write `lecture.present.html`, then archive the input only after that succeeds.

## Completion

Done when `pps notes` has written the Lecture Document, plain views, and `lecture.present.html`, the `/present` teaching pass has been applied if the extractive file is still mechanical, and you have reported output paths plus whether the input was archived. On failure, the Recording stays at its original path unless the command itself printed a partial-archive error.

## Steps

1. Work from the PodleParsesSkewl repository root. Run `python3 -m podleparsesskewl doctor` when the environment is unknown.
2. Resolve the Recording, output folder, transcript sidecar, and archive parent the same way `/parse-skewl` does. Lecture files stay local. Do not upload them.
3. Run the shared command (parse + present + optional archive):

   ```bash
   python3 -m podleparsesskewl notes path/to/lecture.mp4
   python3 -m podleparsesskewl notes path/to/lecture.mp4 -o path/to/out --archive-dir path/to/archive
   python3 -m podleparsesskewl notes path/to/lecture.mp4 --no-archive --offline-transcription
   ```

4. Open the resulting `lecture.json` and `lecture.present.html`. Follow `.agents/skills/present/SKILL.md` for the teaching pass: mental models, applications only when Said supplies them, local diagrams only where the Shown is not enough. Keep image `src` relative. Do not invent Said.
5. Archive is part of `pps notes` (unique run folder, manifest, move not copy). Do not move files yourself. Use `--no-archive` when the captain wants the Recording left in place. Never overwrite an existing archive folder.

If you are a manager agent, dispatch an implementation subagent with the resolved paths and the `pps notes` command, then a second pass that follows `/present`.

## Boundaries

- Same local-only rules as `/parse-skewl`: no cloud API, no bundled models, no committed lecture files.
- Move happens only after `lecture.present.html` exists. If parse or present fails, leave the input where it is.
- `/ezLectures` remains a separate faithful HTML view. Do not substitute it for teaching notes.
- `/teach` and other tutor/workspace skills are a different product. Do not install them for this flow.
