---
name: ezLectures
description: >
  Render an aesthetic HTML lecture-review page from a PodleParsesSkewl
  Lecture Document (lecture.json). Use when the user runs /ezLectures, asks
  for a nicer or prettier lecture HTML, a dressed review page, or an
  aesthetic view of said+shown stills. Do not use this to extract stills or
  transcribe audio - the program already did that.
---

# /ezLectures

Turn an existing Lecture Document into a dressed HTML review page.

## Completion

Done when a single HTML file is written that a person can open in a browser and scan Still by Still, each Shown paired with its Said. Do not extract frames, do not transcribe, do not invent speech or images.

## Steps

1. Locate the Document. Prefer an explicit `lecture.json`. If the user pointed at a `.lecture/` folder or an MP4 whose sibling folder exists, use that folder's `lecture.json`. If several candidates exist, ask which Lecture.
2. Read `lecture.json` as the only source of title, stills, times, and said text. Load the images named in each still's `image` field (paths are relative to the Document folder).
3. Write HTML next to the Document, default name `lecture.ez.html`, unless the user named another path. Keep image `src` relative so the folder stays portable (`stills/still-001.png`).
4. Preserve every Still in order. Do not merge, drop, or invent Stills. Do not rewrite Said except for HTML escaping and light paragraph breaks on existing newlines.

## Layout

One vertical column, readable on a laptop. For each Still:

- the Shown image, full column width, sharp edges
- a quiet timestamp (`HH:MM:SS - HH:MM:SS`)
- a clear rule
- the Said text

Put a stronger break between Stills than between an image and its own transcript. Title at the top. No video player. No nav chrome.

## Look

Quiet study page, not a marketing site.

- Off-white page (`#f6f1e8` or similar), near-black text
- A real serif for Said (e.g. `Iowan Old Style`, `Palatino`, `Georgia`)
- A small sans-serif for timestamps and the title eyebrow
- Comfortable measure, about 40rem, generous line-height
- Images with a thin warm-gray border and slight shadow
- Horizontal rules, not cards stacked in a grid

If you include CSS, keep it in a `<style>` block in the one file.

## Refuse

- Re-running `pps parse` or calling ffmpeg / Whisper
- Summarizing, bulleting, or "improving" the lecture wording
- Fetching images or fonts from the network (system fonts only)
- Scraping `lecture.html` when `lecture.json` is present
