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

Done when a person can open `lecture.present.html` offline and learn the lecture's ideas without re-watching, without Obsidian, and without a network. Every claim is grounded in Said or Shown. Do not extract frames. Do not transcribe. Do not invent speech, numbers, names, or diagrams. After the Signal pass, `lecture.stills-text.json`, `lecture.grades.json` (valid under `pps histogram --check`), `lecture.brief.md`, and `lecture.taught.md` exist beside the Document.

## Steps

1. Locate the Document the same way `/ezLectures` does: an explicit `lecture.json`, a `.lecture/` folder, or the sibling folder of an MP4. If several exist, ask which Lecture.
2. Read `lecture.json` as the only source of title, stills, times, and said text. Load each Still image named in `still.image` (paths relative to the Document folder).
3. Read the Shown images. Do not write from Said alone. The Still is often the real structure of the lecture.
4. Build a topic outline from **body coverage**, not from the first title Still. Consecutive Stills that are one progressive build may become one topic; a full visual change is a new topic. Record which `still.id`s belong to each topic. Do not drop a topic that has a Still or a substantial Said block just because an early outline Still omitted it.
5. For each topic, write teaching notes in the structure below. Ground every claim in Said or Shown. If the lecturer was vague, say so; do not import a textbook.
6. Write one HTML file next to the Document, default name `lecture.present.html`, unless the user named another path. Keep image `src` relative (`stills/still-001.png`). CSS in a `<style>` block. System fonts only.
7. Optional local skeleton: `python3 -m podleparsesskewl present path/to/lecture.json` writes a grounded extractive `lecture.present.html`. Use it as a starting file, then do the teaching pass. Do not treat the skeleton as finished if mental models are still just restated Said.

If you are a manager agent, dispatch an implementation subagent with the Document path and these steps.

## Signal pass

After the teaching pass, grade the Lecture. The program has already written `lecture.signal.json` and `lecture.signal.md` (timing per Still, sliding windows) during `pps parse`. You add the eyes and the judgment. Use the most capable model available; the program never calls a model. Field contracts live in `docs/signal.md`.

8. **Still text.** From the Still images you read in step 3, write `lecture.stills-text.json` (schema `podleparsesskewl.stills-text/v1`): for every Still, the text visible on it as faithfully as you can read it, its heading as `title` (empty if none), and `has_diagram` true when it carries a figure, plot, circuit, image or equation block. Do not paraphrase or summarise; this is transcription of the Shown. Then run `python3 -m podleparsesskewl histogram <lecture.json> --write` so the text-based signals (token count, explanation density, content overlap, tangent flag) are filled in. It reuses the thresholds stored in `lecture.signal.json`, so do not pass threshold flags.
9. **Module context.** If the Lecture folder sits under `modules/<CODE> - <Short>/lectures/`, or the user named a module, run `python3 -m podleparsesskewl modules show <code>` and read the knowledge tree. "Testable" below means testable for that module's exam as the tree describes it. Record `module` and `knowledge_tree` in the grades file; otherwise set both to `null` and grade from the lecture alone.
10. **Read the signal.** `lecture.signal.md` is the overview. Rank windows by `z` and by their high-signal Stills. For a window, read its Stills' rows in `lecture.signal.json` and their Said in `lecture.json`. For a specific Still or a `transition_links` target, read its row, its Said and its image. To find where a phrase was said, search `transcript.md`; its `## HH:MM:SS` headings give the time.
11. **Grade every Still** into `lecture.grades.json` (schema `podleparsesskewl.grades/v1`; fields and rules in `docs/signal.md`). Importance 0 to 3 with the matching category: 0 `noise_admin_or_tangent` (boilerplate, anecdote, admin, off-topic question, dead space), 1 `low_yield_context` (history, analogy, setup rarely tested directly), 2 `core_testable_concept` (definition, architecture, worked example needed for baseline competence), 3 `critical_exam_skill` (derivation, dense mechanism unpacked in speech, explicit exam emphasis). Rules of judgment:
    - A Still marked `prescore_zero` may be graded 0 without inspection, but it must still appear in the file.
    - `suspect_tangent` true: read its Said critically. Anecdote, admin or an irrelevant question is 0 or 1 with `fluff_filtered: true`. A real explanation that merely uses different words than the Still is not a tangent.
    - Long spoken time plus high explanation density plus `has_diagram`: the lecturer is unpacking something not written on the Still. Put the unspoken steps into `actionable_skill` and grade 3.
    - Short spoken time but emphasis hits ("make sure you can derive this"): grade 2 or 3 anyway.
    - Follow `transition_links` and `same_appearance`: a page the lecturer came back to gets credit for the later payoff; say so in `reconciliation_note` when a later window changed your grade.
    - `justification` cites the numbers you used (seconds, revisits, phrases with their time). `actionable_skill` is a specific thing a student must be able to do, and is `null` for grades 0 and 1.
12. **Check.** Run `python3 -m podleparsesskewl histogram <lecture.json> --check`. Fix every `grades:` error it prints and re-run until it exits 0. It also prints the window histogram with the average grade per window; keep it for the brief.
13. **Brief.** Write `lecture.brief.md` (structure in `docs/signal.md`): the window histogram with average grades; the tier-3 checklist with each `actionable_skill`, its linked Stills and the telemetry proof; the tier-2 table; the tier-1 one-liners; the tangent and noise audit with the time it saves.
14. **Taught.** Write `lecture.taught.md` from the whole `transcript.md`, not from the signal slices: what was taught, in order, with timestamps and Still ids; what the student needs to know, prioritised for the module's exam when a module is known (otherwise for the lecture itself) and cross-referenced to the grades and (when known) to knowledge-tree nodes; what the lecturer left vague; and tree nodes to add. It is for the requester and for later agents, so write it to be read first by an agent asked about this Lecture. The "What you need to know" scope is the only part of this report that may later change.

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
- Grading from the signal numbers alone without reading the Said
- Inventing emphasis or exam claims the transcript does not contain
- Editing `lecture.signal.json` by hand
- Calling any model API from the program
