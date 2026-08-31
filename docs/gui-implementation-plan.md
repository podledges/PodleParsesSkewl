# GUI implementation plan

This is the durable GitHub-issue plan for the next Windows launcher work. It is not the GUI itself.

Inspection date: 2026-08-29  
Worktree: isolated `fm/podleskewl-gui-issues-plan` at `ba21d02` (`origin/main`)  
GitHub issues created in [podledges/PodleParsesSkewl](https://github.com/podledges/PodleParsesSkewl). There were no existing open or closed issues covering this work.

## What already exists

There is no `docs/` GUI spec, no ADR, no TODO/FIXME, and no GitHub issue that already tracks this work. What exists is a shipped path-form launcher plus a read-only fleet scout.

### Shipped launcher (source of current behavior)

| Surface | Where | What it is |
| --- | --- | --- |
| Tkinter window | `podleparsesskewl/gui.py` | Four path rows (Recording, output, sidecar, archive), **Parse** and **Parse + Notes**, archive checkbox, indeterminate progress bar, always-visible log, ffmpeg startup modal |
| Workflow bridge | `podleparsesskewl/workflow.py` | `build_parse_argv` / `build_notes_argv` for the GUI; `parse_lecture` / `parse_and_present` for typed results the GUI does not yet consume |
| CLI | `podleparsesskewl/cli.py` | `doctor`, `list`, `parse`, `present`, `notes`, `render`. Stable automation/WSL surface |
| Lecture picker data | `podleparsesskewl/config.py` `list_recordings` | Newest-first MP4/M4V/MOV listing. Used by `pps list` and `--latest`, not by the GUI |
| Environment | `podleparsesskewl/deps.py` | ffmpeg/ffprobe/transcriber inspection used by `pps doctor` and the GUI ffmpeg modal |
| Packaging | `PodleSkewl.spec`, `pps-gui.spec`, `installer/PodleSkewl.iss`, `scripts/build-windows.ps1` | No-console `PodleSkewl.exe` and historical `pps-gui.exe`; Start Menu shortcut; ffmpeg and models stay external |
| Tests | `tests/test_gui_commands.py`, `tests/test_packaging.py` | CLI argv contract the GUI emits today; packaging does not bundle ffmpeg/models |
| Human docs | `README.md`, `WINDOWS-SMOKE-TEST.md` | Describe **Parse** / **Parse + Notes**, browse-for-MP4, archive checkbox, missing-ffmpeg prompt |
| Domain language | `CONTEXT.md` | Recording, Lecture, Still, Shown, Said, Transcript, Document, Report |

Current GUI gaps (confirmed in `gui.py`, not only in the scout):

1. It is a path form, not a workflow. Four fields appear before the user has chosen a Recording.
2. Success is a modal. There is no Open review, Open teaching notes, or Show folder action. `webbrowser` is used only for the ffmpeg download page.
3. Progress is an indeterminate bar. Captured CLI stdout is painted only after `cli.main` returns.
4. Archive success is inferred by searching log text for `Archive   skipped`.
5. Preflight is a startup ffmpeg modal. A Recording with no sidecar and no transcriber is not explained in place.
6. The configured lecture directory is not offered as a recent list.
7. The helper sentence uses a fixed window (`740x620`) and is known to clip.
8. There is no cancel contract. Closing during a run is not modeled.
9. The archive checkbox is always visible and seeded from `config.archive_after_notes` (default true).

### Fleet scout (direction, not a repo spec)

The 2026-08-25 read-only scout at `/home/podles/fleet/firstmate/data/podleskewl-gui-cli-grill-codex/report.md` recommended:

- Keep the native Windows GUI as the primary human interface.
- Keep the current CLI for automation and WSL.
- Do not build an arrow-key TUI for the MVP.
- Turn the form into a three-stage utility: choose Recording, choose Review or Teaching notes, run and open.
- Use an explicit state machine and typed workflow events.

That report also recorded **five unanswered captain questions**. This plan does not treat those recommended defaults as settled.

### What is missing

- A repo-owned GUI specification (this file is the plan, not a locked product spec).
- A testable launcher state model.
- Pipeline/workflow phase events.
- Typed success actions (open HTML, reveal folder).
- A workflow-led window.
- DPI / keyboard / success-action smoke coverage.
- Captain answers for Q1-Q5.

## Assumptions

These are implementation assumptions, not captain decisions.

- The next human interface work stays on the existing Tkinter launcher. Zero core runtime dependencies stay in force (`pyproject.toml`).
- One Recording remains one Lecture. Canonical result remains `lecture.json`. Stills stay Stills.
- The GUI may call `parse_lecture` / `parse_and_present` for typed results. The CLI argv helpers can remain for tests.
- Cooperative cancellation is out of MVP. The window must not fake Cancel.
- ffmpeg, transcription engines, and model files stay external unless Q5 is reversed.
- Linux `unittest` is the automated bar; Windows DPI and installer smoke stay manual as in `WINDOWS-SMOKE-TEST.md`. CI green is not the real MP4 media test.
- If Q1 is reversed to "terminal is primary," issues #10 and #11 are superseded. Issues #7-#9 may still be useful, but the TUI is a new issue set, not a silent extra.

## Open captain choices

Tracked in [#6](https://github.com/podledges/PodleParsesSkewl/issues/6). Implementation issues below are written against the **recommended default**. They must be revised if the captain picks a different option.

| ID | Question | Options | Recommended default |
| --- | --- | --- | --- |
| Q1 | Primary launch habit | A: double-click Windows app. B: Terminal/WSL, add `pps ui` TUI | A. Keep CLI. No TUI yet |
| Q2 | Default success page | A: match chosen mode. B: always notes. C: always faithful review | A. Remember last-used mode |
| Q3 | Recording selection | A: five newest, require a click, plus Browse. B: preselect newest. C: always file picker | A. Highlight newest, do not auto-commit |
| Q4 | GUI archive default | A: off on first GUI run, then remember. B: on (current config default). C: always follow toml | A. Show archive only for Teaching notes |
| Q5 | Setup boundary | A: inline preflight and Retry. B: bundle ffmpeg and/or transcriber | A. Keep media tools external |

Q4 is already a behavior change relative to today's checkbox.

## Recommended MVP (defaults only)

One native window, one task, three stages:

1. Choose a Recording (recent list + Browse). Show transcript source after selection.
2. Choose Review or Teaching notes. Archive controls only for Teaching notes.
3. Run with named phases, then **Open review** / **Open teaching notes**, **Show folder**, **Process another Recording**.

Advanced: output folder, manual sidecar, model, offline mode, still-detection thresholds.

Visual: `vista` ttk theme when present, Segoe UI, one orange accent, no clipped helper text at 100/125/150% scaling.

Deferred: TUI, bundled ffmpeg/models, batch processing, Cancel, web frontend, Document/Report format changes.

## Issue set

### 1. Confirm GUI MVP product choices

- **Issue:** [#6](https://github.com/podledges/PodleParsesSkewl/issues/6)
- **Goal:** Capture Q1-Q5 without pretending the scout defaults are settled.
- **User-visible behavior:** None until answered. Reversing Q1 supersedes the Windows GUI rebuild.
- **Acceptance criteria:** Captain answers or explicitly accepts the defaults; this plan is updated if any answer differs; dependent issues are adjusted or closed as not planned if Q1 selects TUI.
- **Implementation notes:** No code. Comment the chosen option on the issue.
- **Testing notes:** Not applicable.
- **Dependencies / order:** Blocks #10 only if Q1 flips. #7-#9 can start against defaults.
- **Risk notes:** Coding #10 before Q1 is answered can waste the rebuild if the primary path becomes a TUI.

### 2. Add a testable GUI launcher state model

- **Issue:** [#7](https://github.com/podledges/PodleParsesSkewl/issues/7)
- **Goal:** Replace widget booleans and status strings with a pure transition model.
- **User-visible behavior:** None until #10 renders it.
- **Acceptance criteria:** Dedicated module (suggested `podleparsesskewl/gui_state.py`) with states, phases, immutable context, events, and a transition function; no Tk/thread/dialog types; invalid transitions rejected in tests; success carries typed paths; Cancel is not faked.
- **Implementation notes:** Suggested states: `CHECKING_ENV`, `NEEDS_SETUP`, `CHOOSING_INPUT`, `READY`, `RUNNING`, `FAILED`, `SUCCEEDED`. `RUNNING` carries phase: `PREFLIGHT`, `TRANSCRIPT`, `STILLS`, `DOCUMENT`, `PRESENT`, `ARCHIVE`. Current implicit machine is in `gui.py` (`_busy`, button disable, progress, modals).
- **Testing notes:** Drive the public transition function. Do not grep enum names. `nix-shell --run 'python3 -m unittest discover -s tests -v'`.
- **Dependencies / order:** First code issue. Independent of #8 and #9.
- **Risk notes:** Leaking Tk types here makes headless tests and #10 harder. Modeling success as a status string blocks #9.

### 3. Emit typed workflow phase events from parse and notes

- **Issue:** [#8](https://github.com/podledges/PodleParsesSkewl/issues/8)
- **Goal:** Honest named phases at real pipeline boundaries. No invented percentages.
- **User-visible behavior:** CLI unchanged when no callback is passed. GUI (#10) can show Checking Recording, Loading or transcribing Said, Finding Stills, Writing Document and Reports, Archiving input.
- **Acceptance criteria:** Immutable event type; optional callback on `parse_recording`, `parse_lecture`, and `parse_and_present`; default no-op; events at existing `pipeline.py` / `workflow.py` boundaries; archive events only after Document and teaching Report success; CLI syntax and printed paths unchanged.
- **Implementation notes:** Suggested `podleparsesskewl/workflow_events.py`. Do not scrape stdout. Do not add cooperative cancellation here. Stdlib only.
- **Testing notes:** Event order on success, failure-before-archive, and archive-after-success. Use the synthetic MP4 parse path. Assert callback values. Do not treat CI green as the real MP4 media test.
- **Dependencies / order:** Parallel with #7 and #9. Required before #10 can show live phases.
- **Risk notes:** Callbacks will run on a worker thread. Events must be immutable and Tk-free.

### 4. Add Open review and Show folder actions for local Reports

- **Issue:** [#9](https://github.com/podledges/PodleParsesSkewl/issues/9)
- **Goal:** Testable helpers that open a local Report and reveal the Lecture folder from typed workflow paths.
- **User-visible behavior:** Wired in #10. Open review opens `lecture.html`. Open teaching notes opens `lecture.present.html`. Show folder reveals the Lecture directory. Q2 remains open; recommended default is mode-specific primary buttons.
- **Acceptance criteria:** Helpers live outside `gui.py`; default browser for HTML; Explorer on Windows with a non-crashing fallback for Linux tests; missing paths fail clearly; do not open paths that were not in the successful result.
- **Implementation notes:** Use `ParseResult.html_path`, `PresentResult.present_path`, and the Lecture folder from the result. Stop using the `"Archive   skipped"` log scrape as a success signal.
- **Testing notes:** Temp files plus mocked open/reveal. Public helper behavior, not GUI source greps.
- **Dependencies / order:** Independent of #7 and #8. Required by #10's success footer.
- **Risk notes:** Opening a stale path or a JSON sidecar is worse than offering no button.

### 5. Rebuild the Windows launcher as a three-stage workflow GUI

- **Issue:** [#10](https://github.com/podledges/PodleParsesSkewl/issues/10)
- **Goal:** Replace the path-form window with choose Recording, choose result, run and open. Preserve CLI, config, local-only processing, output formats, and archive safety.
- **User-visible behavior:** Recent five Recordings plus Browse; Review vs Teaching notes; archive only for notes, off on first GUI run then remembered (Q4 default); named phases; inline setup/errors; success actions from #9; Advanced disclosure for output/sidecar/model/offline/thresholds; `PodleSkewl.exe` and `pps-gui.exe` still launch the same no-console window.
- **Acceptance criteria:** Terminal is not required for the happy path; default screen is Recording + mode + one primary action; no fake percentages; archive explicit before Start and reflected from typed results; errors keep selections and generated Reports; presentation renders #7; workflow calls return typed objects rather than only `cli.main(argv)`; zero new runtime dependencies; packaging still excludes ffmpeg/models; unit suite passes with the synthetic MP4 test executed.
- **Implementation notes:** Refactor `podleparsesskewl/gui.py`. Populate recent list via `load_config` and `list_recordings`. Use `vista` ttk theme when present. Grid layout, ~720 minimum width, no hard-coded wrap lengths that clip at 125/150% scaling. Remember last-used mode and archive choice in a small GUI preference store without silently changing CLI `archive_after_notes` default true. Close-during-run confirms; it does not cancel.
- **Testing notes:** Recent list, archive disclosure, Start only when READY, success actions use typed paths, failure retains selection, Start disabled while RUNNING. Keep `tests/test_gui_commands.py` unless argv helpers go away. Windows smoke lives in #11.
- **Dependencies / order:** Depends on #7, #8, #9, and Q1 remaining on the Windows app path.
- **Risk notes:** Tk DPI. Background-thread UI hops. Historical `pps-gui.exe` must keep working. If Q1 flips, close this as not planned; do not also build a TUI in the same issue.

### 6. Update docs and Windows smoke coverage for the workflow launcher

- **Issue:** [#11](https://github.com/podledges/PodleParsesSkewl/issues/11)
- **Goal:** Make README and `WINDOWS-SMOKE-TEST.md` match the rebuilt window, including DPI, keyboard-only use, and success actions.
- **User-visible behavior:** Docs describe the three-stage launcher instead of **Parse** / **Parse + Notes**. Skills stay CLI/agent paths.
- **Acceptance criteria:** README Windows section names Start Menu launch, two result modes, archive visibility, external ffmpeg/transcription. Smoke covers launch, recent-list or Browse, both modes, archive on/off, Open/Show folder, missing ffmpeg, missing transcriber, keyboard-only, 100/125/150% scaling, CLI still works, uninstall. Packaging tests still prove ffmpeg/models are unbundled. This plan file stays the issue index; README does not copy the state machine.
- **Implementation notes:** Same PR as #10 is fine if the copy matches the merged window. Update `tests/test_packaging.py` string pins when README/smoke phrases change.
- **Testing notes:** Packaging tests in CI. Real DPI/installer smoke is manual on clean Windows 10/11. Linux unittest cannot prove scaling.
- **Dependencies / order:** After #10, or the same PR.
- **Risk notes:** Stale **Parse** / **Parse + Notes** copy will fail smoke and confuse testers. Packaging tests that pin exact phrases will fail on a docs rewrite.

## Order

```
#6 product choices (open; Q1 can void #10)
     |
     +--> #7 state model -------+
     +--> #8 workflow events ---+--> #10 workflow GUI --> #11 docs/smoke
     +--> #9 output actions ----+
```

Do not implement the GUI in the PR that only lands this plan.

## Out of scope for this plan's issues

- Implementing the GUI in this documentation PR
- Arrow-key TUI (unless Q1 is reversed, which is a new issue set)
- Bundling ffmpeg, Whisper, or model files (unless Q5 is reversed)
- Batch processing
- Cooperative cancellation
- Web frontend or embedded browser
- Changes to Document or Report formats
- Editing or closing unrelated GitHub issues
