---
name: present
description: >
  Turn an existing PodleParsesSkewl Lecture Document into concise teaching
  notes: mental models, real applications, and diagrams only where the Shown
  is not enough. Use when the user runs /present or asks for study notes
  from a lecture.json. Do not use this to extract stills, transcribe audio,
  or produce a faithful said+shown review - /ezLectures and pps render
  already do that.
---

# /present

Turn one Lecture Document into a single self-contained HTML teaching Report. Sibling of `/ezLectures`. Input is `lecture.json`. Output is `lecture.present.html`. Goal is to learn what the lecture meant, not to replay it verbatim.

## Completion

Done when a person can open `lecture.present.html` offline and learn the lecture's ideas without re-watching, without Obsidian, and without a network. Every claim is grounded in Said or Shown. Do not extract frames. Do not transcribe. Do not invent speech, numbers, names, or diagrams.

## Steps

1. Locate the Document the same way `/ezLectures` does: an explicit `lecture.json`, a `.lecture/` folder, or the sibling folder of an MP4. If several exist, ask which Lecture.
2. Read `lecture.json` as the only source of title, stills, times, and said text. Load each Still image named in `still.image` (paths relative to the Document folder).
3. Read the Shown images. Do not write from Said alone. The Still is often the real structure of the lecture.
4. Build a topic outline from **body coverage**, not from the first title Still. Consecutive Stills that are one progressive build may become one topic; a full visual change is a new topic. Record which `still.id`s belong to each topic. Do not drop a topic that has a Still or a substantial Said block just because an early outline Still omitted it.
5. For each topic, write teaching notes in the structure below. Ground every claim in Said or Shown. If the lecturer was vague, say so; do not import a textbook.
6. Write one HTML file next to the Document, default name `lecture.present.html`, unless the user named another path. Keep image `src` relative (`stills/still-001.png`). CSS in a `<style>` block. System fonts only.
7. Optional local skeleton: `python3 -m podleparsesskewl present path/to/lecture.json` writes a grounded extractive `lecture.present.html`. Use it as a starting file, then do the teaching pass. Do not treat the skeleton as finished if mental models are still just restated Said.

If you are a manager agent, dispatch an implementation subagent with the Document path and these steps.

## Note structure (per topic)

Keep it short. A topic that does not earn these blocks should be folded into a neighbor.

1. **Heading** - the idea, not "Still 7".
2. **In a nutshell** - one sentence, no jargon.
3. **Shown** - the Still image(s) for this topic, full column width.
4. **Mental model** - the intuitive picture. Analogy only if it is faithful to what was taught. Label it as a model so it is not confused with a claim.
5. **How it actually works** - the mechanism in the lecturer's framing. Definitions, formulas, steps. If a formula appears, plain-English breakdown of each symbol. No formula-first openings.
6. **Where you would use this** - one real-life or work application. Prefer one the lecturer gave. If they did not give one, omit the section rather than invent a blog-post use case.
7. **Watch for** - pitfalls or "people mix this up with X" only when Said or Shown supports it.
8. **Diagram** - only if the Shown image does not already carry the structure (relationship, process, comparison). Prefer a compact table or labeled ASCII/SVG. Mermaid source is allowed only if rendered to inline SVG or left as readable ASCII. Do not fetch mermaid.js. Do not generate a decorative picture of a classroom.

Prefer capturing the real Shown over drawing a substitute. Never redraw the lecturer's data, equation, or diagram from imagination when the real Still is legible.

## Look

Quiet study page, sibling of `/ezLectures` so a reader can switch between faithful and taught views.

- Off-white page (`#f6f1e8`), near-black text
- Serif for prose (`Iowan Old Style`, `Palatino`, `Georgia`)
- Small sans-serif for timestamps and eyebrows
- Measure about 40rem
- Images with a thin warm-gray border and slight shadow
- Stronger break between topics than between a Shown and its notes
- One file. No nav chrome. No video player.

## Refuse

- Re-running `pps parse` or calling ffmpeg / Whisper
- Uploading the lecture, stills, transcripts, or models
- Generic textbook summaries that could have been written without this Recording
- Inventing numbers, names, applications, or diagrams that contradict the Shown
- Dropping a topic that has a Still or a substantial Said block
- Keeping every "um" and the full transcript (that is `/ezLectures`)
- Obsidian wikilinks, YAML Properties, callouts, or a vault tree
- Network fonts, CDN scripts, or fetched images
- Treating "slide" as a second extracted object; the visual is a Still
