---
name: transcribe
description: Transcribe long local audio or video with PodleParsesSkewl. Use when an agent needs a faithful timestamped transcript artifact without cloud ASR or media upload.
compatibility: Requires PPS_EXECUTABLE and PPS_MODEL_CACHE or PPS_MODEL_PATH as absolute local paths.
---

# Transcribe local media

1. Call `pps_transcribe` once with the explicit local media path. Supply `output` only when the user chose a new destination.
2. Report the returned artifact paths, counts, timings, provenance, and bounded section index.
3. Open `transcript.md` or `lecture.json` only when the current task needs transcript detail. Read targeted sections for hosted-model work rather than returning the full long transcript.

The tool defaults to offline local ASR, auto-selects CUDA when available, and falls back to CPU when CUDA is unavailable. Sidecars remain authoritative. The complete faithful transcript stays in the returned local artifact.
