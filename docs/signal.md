# Timing signal and grades

How Stage 1 (deterministic, inside `pps parse`) and Stage 2 (the `/present` Signal pass) measure and grade a Lecture. Domain terms: `CONTEXT.md`. Thresholds and functions: `podleparsesskewl/signal.py`. Same-page identity: `podleparsesskewl/stills.py` `group_appearances`.

All JSON is UTF-8, `indent=2`, `ensure_ascii=False`, `allow_nan=False`, trailing newline. Times are seconds. Still references use Document ids (`still-001`); indexes are for display and windows only.

## Files

| File | Writer | Role |
| --- | --- | --- |
| `lecture.json` | parser | optional integer `appearance` on each Still, `>= 1`, assigned in first-seen order. Absent or `null` means not recorded. Schema stays `podleparsesskewl.lecture/v1`. |
| `lecture.stills-text.json` | agent | optional sidecar. Schema `podleparsesskewl.stills-text/v1`. Keys are Still ids; unknown ids are an error. `title` and `text` are strings; `has_diagram` is a boolean. |
| `lecture.signal.json` | Stage 1 | machine signal. Schema `podleparsesskewl.signal/v1`. |
| `lecture.signal.md` | Stage 1 | ASCII histograms and a per-Still table. |
| `lecture.grades.json` | agent | importance 0-3. Schema `podleparsesskewl.grades/v1`. Validated by `pps histogram --check`. |
| `lecture.brief.md` | agent | grade-driven study brief. |
| `lecture.taught.md` | agent | full-transcript knowledge report. |

`pps parse` never reads an existing Still-text sidecar. `pps histogram --write` does, when the file sits beside the Document.

## Stage 1 algorithm

Rounding: `round_half_up(x) = floor(x + 0.5)` for `x >= 0`. Integer-second fields use it. Two-decimal fields use `round(x, 2)`.

### Thresholds

Named constants in `signal.py`, recorded on the JSON, a few exposed as CLI flags. `--check` recomputes with the stored thresholds.

| Constant | Default | Flag |
| --- | --- | --- |
| `PAUSE_SECONDS` | 1.5 | `pps histogram --pause-seconds` (`pps parse --pause-seconds` only groups transcript paragraphs) |
| `DEAD_AIR_SECONDS` | 2.0 | |
| `MIN_WORDS_PER_SECOND` | 0.5 | |
| `PASS_THROUGH_SECONDS` | 3.0 | `--pass-through-seconds` |
| `BOILERPLATE_SPOKEN_SECONDS` | 3.0 | |
| `PRESCORE_ZERO_SPOKEN_SECONDS` | 5.0 | |
| `TANGENT_SPOKEN_SECONDS` / `TANGENT_OVERLAP` | 45.0 / 0.15 | |
| `FLUFF_SPOKEN_SECONDS` | 30.0 | |
| `WINDOW_SIZE` / `WINDOW_STRIDE` | 8 / 4 | `--window-size`, `--window-stride` |
| `HIGH_DENSITY_QUANTILE` | 0.75 | |
| `MIN_TOKEN_CHARS` | 3 | |
| `BAR_WIDTH` | 40 | |

Validation: `pause_seconds >= 0`, `dead_air_seconds >= pause_seconds`, `min_words_per_second >= 0`, `pass_through_seconds >= 0`, `window_size >= 1`, `1 <= window_stride <= window_size`.

### Cue noise

A cue is noise when its stripped text is empty; or after removing `[...]`, `(...)`, and `♪` no token contains a letter or digit; or `duration > 0` and `words / duration < MIN_WORDS_PER_SECOND`. A zero-duration cue with words is kept and contributes zero seconds.

### Per-Still time

Cues named by the Still's Sections, non-noise, sorted by start. Clip each to the Still so spoken cannot exceed elapsed. Merge into spoken spans when the gap is `< PAUSE_SECONDS`. Dead-air pauses are gaps (including leading and trailing) `>= DEAD_AIR_SECONDS`. A Still with no spans has one gap equal to its elapsed time.

- `pass_through`: raw elapsed `< PASS_THROUGH_SECONDS`
- `boilerplate`: pass-through, or raw spoken `< BOILERPLATE_SPOKEN_SECONDS`, or the Still title matches the admin-title regex (Agenda, Outline, Thank you, ...)
- `prescore_zero`: boilerplate and raw spoken `< PRESCORE_ZERO_SPOKEN_SECONDS`

### Appearance, visits, links

The parser groups intervals with `group_appearances` using the same `change_ratio` as `segment_stills`. Stage 1 reads `Still.appearance`. When any Still lacks it, visit fields are `null`.

Visible Stills are those that are not pass-through. Consecutive visible Stills with the same appearance are one visit. `visit_count` is the number of visits of that appearance; `revisited` is `visit_count > 1`. `same_appearance` lists the other Still ids in the group. `transition_links` are the visible neighbours of visits after the first whose appearance differs, sorted by index, the same on every Still of the group. Pass-through Stills get `visit_count` 0, `revisited` false, the group's `same_appearance`, and empty links.

### Text signals

Need a sidecar entry. Tokens: casefold, split on non-alphanumeric runs, drop stopwords and tokens shorter than `MIN_TOKEN_CHARS`. `explanation_density = spoken_raw / max(token_count, 1)`. `content_overlap` is the Jaccard-style share of unique Still tokens that also appear in the Said. `suspect_tangent` when raw spoken `> TANGENT_SPOKEN_SECONDS`, overlap `< TANGENT_OVERLAP`, and no diagram. Without a sidecar entry these fields are `null`.

### Emphasis

Case-insensitive whole-word phrases (`exam`, `will be on the`, `make sure you can`, ...). Hits record the canonical phrase, the cue start, and the cue index in `transcript.cues`.

### Windows

Starts `1, 1+stride, ...` while `start <= N`. `last = min(start + size - 1, N)`. Drop a window contained in the previous range. Labels are `1-8`. Spoken totals use non-boilerplate members. `z_score` is that window's mean spoken versus all window means, population standard deviation, or `0.0` when there is only one window or sigma is 0. Peak is the contributing Still with the largest raw spoken time (lowest index on a tie). High-signal Stills are members that are revisited, have emphasis hits, or have explanation density at or above the 75th percentile (nearest-rank, need at least 4 densities).

## Histograms

Pure ASCII. Legend is the first line and names every word that can appear in Notes. Scale `S = max(1, ceil(max_raw / BAR_WIDTH))` seconds per character. Notes, in order: `pass-through`, `boilerplate`, `revisited (also 7, 9)`, `tangent?`, `emphasis xN`, `no text`.

When `pps histogram --check` finds a valid grades file, the window histogram gains `Avg grade` and `3s` columns.

## `pps histogram`

```
pps histogram <lecture.json | .lecture folder>
pps histogram <...> --check
pps histogram <...> --write [--pause-seconds F] [--pass-through-seconds F] [--window-size N] [--window-stride N]
```

Resolves the Document like `present`. Loads `lecture.stills-text.json` from the Document folder when present. Default prints both histograms. `--check` compares a recomputation with `lecture.signal.json` (every field except `generated_at`) and validates grades when present; exit 1 on any difference or grade error. `--write` overwrites the two signal files. Without threshold flags, printing and `--write` reuse the thresholds stored in an existing `lecture.signal.json` (defaults otherwise); each explicit flag overrides its stored value. `--check` with `--write` or with threshold flags is a usage error. There is no `-o`; files always sit beside the Document.

Grade errors fail `--check`. Warnings (printed, do not fail): `fluff_filtered` on a Still whose spoken time is at or below 30 s; a `prescore_zero` Still graded above 0; `signal_generated_at` older than the stored signal.

## Grade schema

Every Document Still appears exactly once. `importance` is `0, 1, 2, 3` (booleans rejected). Category must match: 0 `noise_admin_or_tangent`, 1 `low_yield_context`, 2 `core_testable_concept`, 3 `critical_exam_skill`. `actionable_skill` is `null` when importance `<= 1` and a non-empty string when `>= 2`. `fluff_filtered` is a boolean and true only when importance `<= 1`. `linked_stills` are existing ids, not the Still itself, no duplicates. `core_topic` and `justification` are non-empty strings. `module` and `knowledge_tree` are both set or both `null`.

## Stage 2 files the agent writes

`lecture.brief.md`: title, window histogram with average grades, tier-3 checklist, tier-2 table, tier-1 one-liners, tier-0 audit with skippable time.

`lecture.taught.md`: what was taught, in order, with timestamps and Still ids; what the student needs to know, prioritised for the module's exam when a module is known (otherwise for the lecture itself); where the lecturer was vague; knowledge-tree nodes to mark or add. Grounding rules are those of `/present`. The "What you need to know" scope is the only part of this report intended to stay easy to change.
