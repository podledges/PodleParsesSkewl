---
name: module
description: >
  Resolve which study module the user means (code, bare number, nickname),
  show or update that module's knowledge tree, add modules or aliases, and
  keep the private modules clone in sync across machines. Use when the user
  runs /module, mentions a module while working, asks to show a knowledge
  tree / plan / map / prerequisite list for a module, or drops coursework
  for a module. Not for parsing recordings (/parse-skewl) or writing
  teaching notes (/present).
---

# /module

Work from the PodleParsesSkewl repository root. Modules are the folders in `modules/`, a clone of the private modules repo; the registry is `modules/*/module.json`; the format reference is `docs/modules.md`. Never commit anything under `modules/` to PodleParsesSkewl, and never put received course material anywhere but `material/`, or `lectures/` for parsed `*.lecture` folders.

## Completion

Done when the mention is resolved to exactly one module (or a new one is created with the user's yes), the requested action on that module's `knowledge-tree.md` is done, any new alias is persisted with `pps modules alias`, and `pps modules sync` has run after the last edit with no conflict left open.

## Steps

0. Sync. On the first module action of the session run `python3 -m podleparsesskewl modules sync`. Sync pulls with rebase and autostash, regenerates the table, commits local edits, then pushes. If it exits 1, it names the conflicted files. A rebase conflict: resolve the markers (for `MODULES.md`, take either side and do not hand-merge it; the next sync regenerates it), `git -C modules add` them, run `GIT_EDITOR=true git -C modules rebase --continue`, and sync again. An autostash re-apply conflict, where the rebase already finished: resolve the markers, `git -C modules add` the files, run `git -C modules stash drop`, and sync again. If it says `modules/` is missing, tell the user the one-time `pps modules init <url>` step from `docs/modules.md` and stop. Then read `modules/MODULES.md`.
1. Resolve. If the mention is a code, bare number or alias in `MODULES.md`, use it. Otherwise run `python3 -m podleparsesskewl modules resolve "<mention>" --json`.
   - `resolved` by code, number or alias: proceed silently.
   - `resolved` by fuzzy: proceed, and say in one line which module you took it as.
   - `suggest`: ask "<CODE> <short>?" in one line. Yes: proceed and, unless `matched_by` is `near-code`, run `pps modules alias <CODE> "<mention>"`. No: go to step 2.
   - `ambiguous`: list the candidates in one line and ask which. Persist the answer as an alias, unless the mention is a code, bare number or digit near-miss (`matched_by` `code`, `number` or `near-code`).
   - `unknown`: go to step 2.
2. Semantic pass. Read the candidate list and the table. If one existing module clearly fits (a nickname, an abbreviation, a topic that belongs to it), propose it in one line and, on yes, persist the alias. If nothing fits, ask whether this is a new module and for its code and full title if missing.
3. New module. Derive Short by the naming rule in `docs/modules.md` (abbreviation first, else first two content words), propose `<CODE> - <Short>`, and on yes run `pps modules add <CODE> --title "<title>" --short "<Short>"`. Then start its tree (step 5).
4. Show. For "show / print / give me the <module> tree / plan / map / list": run `pps modules show <mention>` and return its output as is. Do not summarize, reorder or embellish.
5. Edit. For progress ("3.4 done", "I understood convolution"), new nodes, open questions or reading order: edit `knowledge-tree.md` in place following its grammar (`- [ ]` / `- [x]`, children are prerequisites, pages as printed / PDF), update `Updated:`, append a Log line with today's date, print the changed node, then run `pps modules sync`.
6. Material. When the user adds received course material (textbook, slides, past papers, recordings) for a module, put it under that module's `material/` (or `lectures/` for `*.lecture` folders) and say where. The user's own work (assignments, code, solutions) goes in `work/`, which syncs. Never move received material into a tracked path.

If you are a manager agent, dispatch an implementation subagent with the resolved module folder and the step to run.

## Boundaries

- One module per mention. Do not guess between two candidates; ask.
- Persist aliases only after the user confirmed or corrected; never persist a digit near-miss such as `4714`.
- Do not edit `module.json` or `MODULES.md` by hand when `pps modules add`, `alias` or `sync` can do it.
- Sync is safe to run any time; run it after every edit, not only at the end. Do not run `git push` by hand inside `modules/` when `sync` exists.
- The tree is the student's prerequisite map, not a syllabus copy. Add nodes the student needs, with where to read them. No textbook text, no copied slides.
- Domain terms live in `CONTEXT.md`. A Module is the course; a Lecture is one Recording; a Still is the extracted visual.
