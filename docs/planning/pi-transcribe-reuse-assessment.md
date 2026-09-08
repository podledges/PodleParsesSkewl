# Pi `/transcribe` reuse assessment

> **Status:** Investigation and proposal only. This document does not implement or approve `/transcribe` V1.
>
> **Recorded evidence:** 2026-09-08, against PodleParsesSkewl revision [`0cb4df9`](https://github.com/podledges/PodleParsesSkewl/commit/0cb4df93c25f76a0c8f3cb5ff29415e54d6c24d7) and Pi 0.85.1. Statements about existing behavior and test results refer to that revision unless noted otherwise. Proposed work remains subject to product approval.

## Executive answer

Reuse PodleParsesSkewl (PPS); do not build another transcriber. PPS already owns local ASR, ffmpeg audio extraction, timed cues, sidecar ingestion, visual change detection, canonical `lecture.json`, and faithful Still/Said reports.

The requested V1 is **not packaging-only**. At the assessed revision PPS lacked:

- audio-only orchestration;
- pause-based transcript grouping;
- a faithful transcript-only paragraph/heading renderer; and
- the requested comparison of visual state at *t* with approximately *t−30 seconds*.

The smallest useful integration is a Pi package with a thin TypeScript command/tool bridge and a small skill, invoking the existing PPS Python runtime. A packaging-only pilot could expose MP4/MOV → current `lecture.json` plus Still/Said reports, but must not be described as the requested `/transcribe` V1. Synthetic evidence showed that MP3 failed, a five-second speech gap remained one paragraph, and a Document with no Stills rendered no transcript in the existing reports.

## Evidence boundary

The investigation read the processing, CLI, configuration, dependency, test, and skill code at the recorded revision, plus the relevant installed Pi extension/package/skill/process documentation. It used only synthetic media. No real-lecture ASR quality was re-measured, no native Windows execution occurred, and no network APIs, package installs, model downloads, or product changes were involved.

The full test suite historically reported **140 passing tests**, including the synthetic MP4 end-to-end parse with ffmpeg present. This is investigation evidence from the recorded revision—not a claim that this documentation change reran those tests, implemented the gaps below, or made the proposed acceptance tests pass.

## Existing capabilities and gaps

| Requirement | At the recorded revision | Evidence and implication |
|---|---|---|
| Explicit MP4 path | Implemented | [`cli.py`](../../podleparsesskewl/cli.py) and [`pipeline.py`](../../podleparsesskewl/pipeline.py); synthetic MP4 parse passed. |
| Explicit MOV path | Implemented, codec-bounded | A synthetic MOV containing MPEG-4 video parsed. ffmpeg decoder support, not suffix alone, determines compatibility. |
| MP3/audio-only workflow | Missing | A real synthetic MP3 with a valid SRT failed with `Recording has no video stream`; [`pipeline.py`](../../podleparsesskewl/pipeline.py) rejected it before transcript loading. |
| Reusable audio extraction | Implemented | [`media.py`](../../podleparsesskewl/media.py) already extracts mono 16 kHz WAV with `-vn`; extraction from the MP3 succeeded. |
| Document without visuals | Partial | [`document.py`](../../podleparsesskewl/document.py) accepts empty Stills/Sections and retains cues, but the pipeline rejected audio-only input and [`report.py`](../../podleparsesskewl/report.py) omitted cues when there were no Stills. Do not invent a black placeholder Still. |
| Local ASR | Implemented | [`transcribe.py`](../../podleparsesskewl/transcribe.py) supports local faster-whisper, openai-whisper, and CLI engines. A bridge should reuse this rather than add Gemini, another ASR, or a web service. |
| Offline readiness everywhere | Partial/unverified | Offline flags exist, but `doctor` checks imports/binaries rather than proving that a compatible model is cached and loadable. Arbitrary hosts and fallback engines were not established. |
| Timed cues | Implemented | Canonical `Cue(start_seconds, end_seconds, text)` data is reusable; do not ask an LLM to recreate timing. |
| Faithful transcript headings/paragraphs | Partial | Current reports are Still-led. Cue text is retained, but alignment space-joins cues per Still and provides neither pause grouping nor transcript headings. |
| Conversation-pause grouping | Missing | ASR VAD filters audio for recognition; it does not create PPS transcript sections. Two cues at 0–1s and 6–7s remained one Said block in one Still. |
| Existing visual segmentation | Implemented | [`stills.py`](../../podleparsesskewl/stills.py) provides sampling, block-change comparison, threshold, and hold machinery. |
| Compare *t* with *t−30s* | Missing | The comparator used the first/last accepted Still as its anchor, not a rolling 30-second reference. This requires a named new mode rather than a sampling-rate or threshold tweak. |
| Faithful Still/Said alignment | Partial | Midpoint cue assignment was tested, but an off-tick transition produced a later Still whose PNG still showed the preceding visual state. This timing bug must be fixed before video boundaries are promised as reliable transcript structure. |
| Pi `/transcribe` and model tool | Missing | The repository had no Pi package/extension or `/transcribe` command. Existing skills are instructions, not registered tool APIs. |
| Progress, cancellation, structured errors | Partial | The CLI returned final human output and exit status. It did not provide long-job phase events or a process-tree cancellation contract. |
| YouTube | Missing, proposed V2 | Keep URL ingestion out of V1. |

### Containers and sidecars

Explicit `pps parse <path>` did not enforce a filename allowlist: representative synthetic MP4, MOV, M4V, MKV, and an MP4 renamed `.bin` parsed. This does not establish support for every codec, encrypted media, or MOV variant. By contrast, recording discovery listed only `.mp4`, `.m4v`, and `.mov`.

Stream probing must decide audio-only behavior. An audio file with attached cover art is an important acceptance case: artwork must not become a fabricated visual section. Sidecars remain authoritative in their existing precedence (`.srt`, `.vtt`, `.webvtt`, `.json`); invalid sidecars should fail clearly rather than silently triggering ASR.

## Synthetic counterexamples

These results exercise current functions and ffmpeg rather than replacement processing:

```text
MPEG-4 video: .mp4 / .mov / .m4v / .mkv / renamed.bin each parsed,
              producing 2 Stills and 2 cues
MP3 + SRT: failed with "Recording has no video stream"
MP3 probe: duration=8.0, width=None, height=None,
           has_audio=True, has_video=False
MP3 lower-layer WAV extraction: 256,078 bytes
Cues 0–1s and 6–7s in one Still: one Section and one joined Said block
Audio Document with no Stills/Sections: JSON round-trip retained both cues
Markdown for that Document: title and metadata only; transcript omitted
Slow visual drift: accepted Still boundaries [0.0, 62], while every
                   rolling lag-30 changed-block ratio was 0.0
Off-tick red→blue cut at 4.2s: later Still started at 4.0s but its PNG
                               remained red; actual video at 5s was blue
```

The off-tick result is a substantive Still timing bug. The existing pipeline test checked that the PNG existed, not that its pixels represented the new interval, so the historical green suite does not disprove it.

## Faithfulness and locality

A transcript Report should be deterministic and sourced from `document.transcript.cues`, not Still-aligned `sections[].said`, HTML scraping, `/present`, or an LLM rewrite. Preserve every nonempty cue exactly once and in order, modulo documented whitespace joining/escaping. Do not remove filler, correct technical names, generate topic titles, summarize, translate, or add speakers. Cue timestamps are spans, not word timing or diarization; a cue crossing a visual boundary should not be presented as word-accurately split.

Recommended bridge defaults are explicit offline mode, an explicitly configured local model/cache, local file input only, and no model acquisition or media upload. A successful local-ASR smoke loaded a pre-provisioned faster-whisper base model and ran VAD over synthetic silence with network access blocked; it ended with the expected no-speech error. That proves one cache/load/VAD path, not successful speech recognition, transcription accuracy, all native network paths, or fallback-engine readiness.

Local ASR does not make a hosted Pi conversation local. Returning transcript text to a hosted model can disclose it. By default the tool should return only artifact paths, counts, timings, provenance, and bounded diagnostics; the complete faithful transcript remains a local file. Strictly local model reasoning requires an appropriate local Pi provider.

## Proposed V1, pending approval

The following is implementation-ready guidance, **not approved or implemented work**.

### PPS behavior slice

1. Add a narrow `pps transcribe` command/service that reuses probing, transcript loading, `TranscriptionOptions`, canonical Document writing, and existing video processing. Refactor shared orchestration rather than copy the parse pipeline. Preserve `pps parse` defaults and behavior.
2. Accept supported local media according to probed streams. For audio-only input, run existing sidecar/ASR processing and write a canonical Document with no Stills or Sections. Never manufacture a Still to satisfy an old renderer.
3. Add a sibling `transcript.md` Report sourced directly from cues. A proposed format is `## HH:MM:SS` at the first cue of each group, whitespace-only joining, and paragraph boundaries only at cue boundaries. Very long uninterrupted groups may split at a bounded cue-level size (for example, about 120 words) without claiming a topic change.
4. Group on timed cue gaps using a configurable initial threshold (proposed: 1.5 seconds between one cue's end and the next cue's start). This is a timestamp-gap approximation, not proven acoustic silence. For “pauses and/or visuals,” use pause **OR** visual boundary and deduplicate. Audio-only uses gap/size boundaries only.
5. If V1 promises the requested lookback behavior, add a named optional lookback mode to existing sampling/segmentation. Compare samples near *t* and *t−30s*, retain the existing block metric and hold concept, and coalesce sustained differences. Pin behavior for warmup, return-to-prior-state, and rapid changes. Keep ordinary parse detection unchanged. A smaller pause-only release is feasible but must say that lookback is not delivered.
6. Fix representative-frame timing and add pixel regressions before using visual boundaries as dependable headings. Treat attached pictures separately from moving video.

The pause threshold, paragraph size, and lookback details are proposed tunables, not user-approved constants. Filler editing, diarization, hosted-chat transcript delivery, automatic model acquisition, or mandatory separate-agent processing would change the privacy/cost/product boundary and require separate approval.

### Thin Pi bridge

Proposed package surface:

- `/transcribe <path>` registered as a Pi command for explicit local paths;
- a distinct model-callable `pps_transcribe` tool;
- a small `transcribe` skill that invokes the tool and preserves artifact provenance; and
- one child process invoking an explicit PPS Python executable with argv passed separately, never shell-concatenated.

The bridge should not become a server or second processing implementation. It must work from unrelated project directories without relying on ambient `PYTHONPATH`, whichever `python` wins `PATH`, `--latest`, or cwd-discovered output/archive configuration.

For the existing video-only pilot, Pi's bounded `exec` helper may suffice. Full V1 should use a small spawned-process adapter with streamed, honest phases (`checking`, `processing`, `validating`, `done`), unique staging, bounded output, and tested process-tree termination. The investigated Pi helper killed its immediate parent after abort but left a spawned descendant alive; cancellation must therefore be verified across the complete Python→ffmpeg process tree, not inferred from a `killed` flag or exit code.

A proposed PPS machine contract is versioned JSON/JSONL containing artifact paths, source, duration/counts, warnings, and exactly one final result. Existing human CLI output need not change. Reject or explicitly queue concurrent ASR work initially. Publish artifacts only after validating the result/schema/files; clean only bridge-owned staging. Map missing runtime/model/ffmpeg, unsupported streams, no speech, bad sidecars, malformed output, nonzero exit, abort, and write failures to actionable errors. Never retry via cloud or treat stale artifacts as success.

A separate LLM worker is optional only when the host already supplies a trusted delegation tool and loads this package for that worker. It is not required for deterministic transcription, and no custom agent framework, daemon, scheduler, MCP server, provider switch, or mandatory second model call is proposed.

### Host limitations

Pi package installation does not provision Python, ffmpeg, or ASR models. Runtime, executable, model, input, and output paths must be explicit and appropriate for the child OS. The assessment exercised NixOS/WSL, not native Windows. Linux Python should normally use Linux ffmpeg under WSL; mixed Windows/Linux argv, UNC paths, nonstandard mounts, native Windows process-tree cancellation, wheel compatibility, and actual speech recognition remain validation gaps.

## Proposed acceptance tests

These are required promotion tests, not claims about the current suite:

| Test | Required assertion |
|---|---|
| Existing behavior regression | Existing suite remains green with ffmpeg present and synthetic MP4 E2E not skipped. The count of 140 is historical and may change as tests are added. |
| Media stream matrix | Generated MP4/MOV plus MP3 and audio-only MP4/MOV produce valid `lecture.json` and `transcript.md`; audio-only and attached-art cases have no Stills/visual headings. |
| Gap heading and coverage | Cues around the configured threshold produce exact expected headings; every cue appears once. Cover exact/below threshold, overlaps, Unicode, punctuation, long speech, >1-hour times, and invalid timing. |
| Faithful transcript | Filler, repetition, numbers, technical names, and Markdown-like text survive modulo documented whitespace/escaping; no generated topics or omissions; files over 50 KB remain complete on disk. |
| Lookback is not anchor | Slow grayscale drift differentiates lookback and anchored modes; no cut occurs at 62s when every lag-30 ratio is zero. |
| Lookback coalescing | Held swaps, flickers, A→B→A, close transitions, warmup, and end-before-hold have pinned behavior without repeated headings; pause OR visual merging never duplicates/drops cues. |
| Still image timing | In red 4.2s→blue 4s video, the later Still's representative PNG is blue; repeat between sample ticks and at non-1fps rates. |
| Offline runtime preflight | Missing/unimportable runtime, ffmpeg, and missing/incompatible/corrupt model caches fail clearly without download, upload, or cloud fallback. |
| Real ASR opt-in smoke | With approved locally generated speech and a pre-provisioned model under blocked network, phrases are plausibly recognized with finite timing and silence creates no invented prose. Record versions/model and keep distinct from mocked tests. |
| Cross-project Pi registration | Isolated Pi state discovers command, tool, and skill from an unrelated cwd without global writes, real model calls, or inherited `PYTHONPATH`. |
| Command/tool dispatch | Quoted Unicode paths, missing paths, busy sessions, tool args, normalization, and untrusted source text are handled without recursion, shell interpretation, or mandatory delegation. |
| Errors and truncation | UTF-8 chunking, >50KB logs, exit 2, malformed JSON, missing artifacts, and spawn errors yield bounded updates and correct failures while the local transcript remains complete. |
| Whole-job-tree abort | Pre-start, mid-run, finish, reload, and shutdown aborts leave no fake Python child or grandchild alive and clean only owned staging on POSIX and native Windows. |
| Paths and overwrite | Same stems, parallel requests, hostile shell characters, Windows/WSL paths, and read-only output cause no collisions, input movement, or unintended writes. |
| Mode smoke tests | TUI, print/JSON, and RPC modes do not depend on dialogs; UI calls are guarded; optional delegation works when present and falls back cleanly when absent. |

## Decision summary

The reusable core is strong enough to avoid a second transcriber. Promotion should pair a small PPS behavior slice with a thin Pi bridge. Audio-only orchestration, faithful cue-led rendering, explicit pause grouping, honest visual lookback semantics, and the reproduced Still timing fix are product work still awaiting approval. This assessment records the evidence and proposal; it does not authorize implementation or close the broader V1 decision.
