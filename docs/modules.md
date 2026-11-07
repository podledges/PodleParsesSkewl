# Study modules

A Module is one taught course, with a code and a title (`EE4704`, Image Processing and Analysis). Its knowledge tree is the list of what to know and what to read first. Both live in a private GitHub repo, [podledges/PodleModules](https://github.com/podledges/PodleModules), cloned at `modules/` inside every PodleParsesSkewl checkout. This public repo ignores `modules/`. Nothing under it is committed here.

The same clone is the working copy on the Mac and on the Windows PC under WSL. `pps modules sync` pulls, commits local edits, and pushes, so the other PC is current at its next sync. There is no `data/` folder. `docs/` is this public manual. Private records that belong to no single module go in `modules/_project/` and sync with the clone.

`pps` is the `python3 -m podleparsesskewl` entry point. The agent protocol is the `/module` skill (`.agents/skills/module/SKILL.md`).

## Layout

Only a directory whose name matches `<CODE> - <Short>` is a module. `MODULES.md`, `README.md`, `_project/`, and `.gitignore` at the clone root are not modules.

```
modules/                                      # clone of podledges/PodleModules
  .gitignore                                  # */material/  */lectures/  .DS_Store
  README.md
  MODULES.md                                  # generated table; do not edit by hand
  _project/                                   # private records for no single module
    prompts.md
  EE4704 - Image Processing/
    module.json                               # code, title, short, aliases, status
    knowledge-tree.md                         # the tree
    README.md                                 # optional: goals, exam info, where material lives
    work/                                     # the student's own coursework (tracked, synced)
    material/                                 # received course material (ignored, never uploaded)
    lectures/                                 # parsed <name>.lecture/ folders (ignored)
  CG2271 - RTOS/
    module.json
    knowledge-tree.md
```

`work/` syncs. `material/` and `lectures/` do not. Received course material (textbooks, slides, past papers, recordings, parsed lectures) stays in those ignored folders on the machine that has it. It is never committed or uploaded, including to the private repo. A dropped PDF under `material/` stays local because the private repo ignores `*/material/` and `*/lectures/`. Force-adding a received file is not the default, and a textbook is never a candidate for it.

The student's own assignments, code, and solutions go in `work/`.

Link a file that already lives on the Windows disk into the ignored material folder. Do not copy it:

```bash
ln -s "/mnt/c/Users/ayden/Downloads/Digital Image Processing.pdf" \
  "modules/EE4704 - Image Processing/material/"
```

## Where a file goes

| Folder | Repo | Holds |
| --- | --- | --- |
| `docs/` | public | How the tool and the module system work. A stranger who clones PodleParsesSkewl needs it to operate the system. |
| `modules/<CODE> - <Short>/` | private | Everything about one module: tree, manifest, optional README, `work/` (synced), `material/` and `lectures/` (local only). |
| `modules/_project/` | private | Private records that belong to no module: the prompt log, an exam timetable, a copied planning note. |
| `data/` | none | Not used. A local-only folder would not reach the second PC. |

Module files go in that module's folder. Private records that belong to no module go in `modules/_project/`. `docs/` is only for how things work.

## The private clone

The private repo's root is the module list. A clone at `./modules` is the layout above. No symlink, no submodule, no config pointer. The public `.gitignore` line is `modules/`. A nested clone under that ignored folder is invisible to this repo.

The private repo's own `.gitignore` is `*/material/`, `*/lectures/`, and `.DS_Store`.

Parsed lectures for a module (`lectures/<name>.lecture/`) stay local, the same way other `*.lecture/` output stays local. They are large and can be rebuilt from the Recording.

The Windows GUI does not know about modules. Module work on the Windows PC is the WSL checkout.

### Once per machine

Create the private repo and its first content separately. This manual assumes `git@github.com:podledges/PodleModules.git` already exists.

On the Mac, from a PodleParsesSkewl checkout:

```bash
python3 -m podleparsesskewl modules init git@github.com:podledges/PodleModules.git
python3 -m podleparsesskewl doctor
```

On the Windows PC, inside WSL, from a checkout on the WSL filesystem (for example `~/PodleParsesSkewl`, not under `/mnt/c`):

```bash
gh auth login
cd ~/PodleParsesSkewl
python3 -m podleparsesskewl modules init git@github.com:podledges/PodleModules.git
python3 -m podleparsesskewl doctor
```

`gh auth login`, or an SSH key on the GitHub account, is once per machine. Keep both checkouts on a native filesystem so git is fast and folder names that contain spaces behave.

`pps modules init <url>` clones that URL into `modules/` when the folder is absent, checks that the remote and the layout match, and prints the doctor Modules block. It is a no-op when `modules/` is already a clone of that remote. It exits 2 when `modules/` exists and is not a clone of that remote.

### Sync

There is no daily command to run by hand. `/module` runs `pps modules sync` at the first module mention of a session and again after every tree edit, module add, or alias. An edit made through an agent lands on GitHub within that sync, and the other PC picks it up at its next sync. A file edited by hand in an editor is published by one `pps modules sync`.

`pps modules sync` does this, in order:

1. Refuse, and point at `init`, when `modules/.git` is missing. Refuse, and name the files, when unmerged files or a rebase are already in progress. It does not pull in that state.
2. `git -C modules pull --rebase --autostash`. Any pull failure other than a conflict, network or not, is a warning, not an error: `pull failed (offline, using local copy): ` followed by git's own message. Sync then continues with the local copy: it regenerates, commits, and tries to push. Read git's message in that warning, because a non-network failure, such as untracked files that would be overwritten, needs a manual fix before the next sync. A missing upstream on the first push is not that warning; the push publishes the branch.
3. When the pull leaves unmerged files or a rebase in progress, print those files and exit 1. See Conflicts.
4. Regenerate `modules/MODULES.md` from the manifests.
5. When `git -C modules status --porcelain` is non-empty: `git -C modules add -A` and commit as `study: <YYYY-MM-DDTHH:MMZ> <hostname>`. The tool does not set a git author; the machine's git config applies.
6. `git -C modules push`. The first push of a new clone sets the upstream. A push failure is a warning (`push failed; commits kept locally for next sync`). The commit stays local and the next sync pushes it.
7. Print one line: `Modules   up to date`, `Modules   pulled 2, pushed 1`, or, when a warning was printed, `Modules   local copy ready; sync incomplete`.

The command is safe to run at any time. It is a no-op when the clone is clean and already matches the remote. Do not `git push` by hand inside `modules/` when `sync` is available. `show` does not sync by itself.

### Conflicts

`sync` exits 1 and lists the conflicted files in both of these cases. Nothing is lost in either one.

A rebase conflict means the pull is replaying a local commit and stops with conflict markers. Resolve hand-edited files (Markdown or small JSON) and `git -C modules add` them. For `MODULES.md`, do not hand-merge a generated table: take either side (`git -C modules checkout --theirs -- MODULES.md` or `--ours`) and `git -C modules add` it. The next sync regenerates the table from the manifests. Then run `GIT_EDITOR=true git -C modules rebase --continue`, so no commit-message editor opens, and run `pps modules sync` again. The local commit stays in the rebase until that continue. `git -C modules rebase --abort` restores it if the edit should be redone instead.

An autostash re-apply conflict means the rebase finished and re-applying the uncommitted edit conflicted. There is no rebase to continue. The edit is in the working tree and still in the stash. Resolve the markers in the listed files; for `MODULES.md`, do not hand-merge it either: take either side (`git -C modules checkout --ours -- MODULES.md` or `--theirs`) and the next sync regenerates the table from the manifests. `git -C modules add` the files, then `git -C modules stash drop`, and run `pps modules sync` again. Dropping the stash removes only that saved copy, after the resolved files are in the working tree. The next sync commits those files.

A hand-edited file conflicts when the same lines were changed on both PCs with no sync in between. `MODULES.md` can also conflict when both PCs have committed a regenerated table, even if they changed different modules, because the sorted rows sit next to each other.

## Folder names

The folder is `<CODE> - <Short>`. Agents quote the path. The CLI resolves it, so the folder name is not something to type by hand.

CODE is upper case and matches `^[A-Z]{2,3}[0-9]{4}[A-Z]?$` (`EE4704`, `CG2271`, `CS1010S`).

Short is at most 32 characters, drawn from letters, digits, spaces, `&`, `+`, and `-`. The command checks the format, the length, and uniqueness. Choose Short like this, then create the folder only after a yes:

1. If the title, or the field it names, has a widely used abbreviation, use the abbreviation: RTOS, VLSI, DSA, DSP, OS, ML, AI, DBMS.
2. Otherwise drop a lead-in phrase: "Introduction to", "Intro to", "Fundamentals of", "Principles of", "Foundations of", "Topics in", "Elements of".
3. If two or fewer content words remain, keep the whole remaining title, including connectors.
4. Otherwise take the first two content words in title order. Content words are nouns and the adjectives that form a compound with them. Connectors (and, of, to, for, in, with) do not count.

The confirmed short name is stored in `module.json` as `short` and is not derived again. `short` must equal the folder name after `<CODE> - `. `pps modules check` fails when they differ.

| Code | Title | Short | Folder | Rule |
| --- | --- | --- | --- | --- |
| EE4704 | Image Processing and Analysis | Image Processing | `EE4704 - Image Processing` | 4 |
| CG2271 | Real-Time Operating Systems | RTOS | `CG2271 - RTOS` | 1 |
| EE5518 | VLSI Digital Circuit Design | VLSI | `EE5518 - VLSI` | 1 |
| CS2040 | Data Structures and Algorithms | DSA | `CS2040 - DSA` | 1 |
| EE2026 | Digital Design | Digital Design | `EE2026 - Digital Design` | 3 |
| CS2105 | Introduction to Computer Networks | Computer Networks | `CS2105 - Computer Networks` | 2 then 3 |
| EE2023 | Signals and Systems | Signals and Systems | `EE2023 - Signals and Systems` | 3 |
| MA1511 | Engineering Calculus | Engineering Calculus | `MA1511 - Engineering Calculus` | 3 |
| EE3331C | Feedback Control Systems | Feedback Control | `EE3331C - Feedback Control` | 4 |

Spaces in the folder name are intentional.

## Manifest and MODULES.md

`modules/<folder>/module.json`:

```json
{
  "code": "EE4704",
  "title": "Image Processing and Analysis",
  "short": "Image Processing",
  "aliases": ["img analysis", "image", "dip"],
  "status": "active",
  "added": "2026-11-07"
}
```

- `code` is unique across modules and matches the CODE pattern above.
- `short` equals the folder name after `<CODE> - `.
- `aliases` are lower case, normalized the same way a mention is (see Resolving a mention), unique across every module, each at least three characters, and none of them a bare code or number. `pps modules alias` writes them. Do not edit the JSON by hand when that command exists.
- `status` is `active`, `paused`, or `done`. The default is `active`.
- `added` is an ISO date, informational.

One manifest per folder. The set of `module.json` files is the registry.

`modules/MODULES.md` is generated by `sync`, `add`, and `alias`. It is sorted by code. Generating it again when nothing changed changes nothing. Edit the manifests, not the table.

```markdown
<!-- generated by `pps modules sync` from */module.json; edit the manifests, not this table -->
# Modules

| Code | Module | Folder | Status | Aliases |
| --- | --- | --- | --- | --- |
| CG2271 | Real-Time Operating Systems | `CG2271 - RTOS/` | paused | rtos, real time os, operating systems |
| EE4704 | Image Processing and Analysis | `EE4704 - Image Processing/` | active | img analysis, image, image processing, dip |
| EE5518 | VLSI Digital Circuit Design | `EE5518 - VLSI/` | paused | vlsi, chip design |
```

Aliases are in the table because the file is private and read on demand. A session that has read it can resolve a nickname it can see there. Anything it cannot see goes to `pps modules resolve`.

## Knowledge tree

Path: `modules/<folder>/knowledge-tree.md`. One file per module. Plain Markdown. The grammar promises are the headings below and the task-list checkboxes.

```markdown
# EE4704 - Image Processing and Analysis: knowledge tree

Goal: pass the EE4704 exam; understand segmentation well enough to design a better lecture parser.
Source: Gonzalez and Woods, Digital Image Processing, 4th ed. Local copy: material/Digital Image Processing.pdf (never uploaded).
Updated: 2026-11-07

## Tree

A node is a thing to know. Its children are what to read or know first. Siblings are in suggested order.
- [ ] 10 Image segmentation (699 / 701)
  - [x] 10.1 Fundamentals (700 / 702): predicate Q, connected, 4/8-connectivity
    - [ ] 2.5 Pixel relationships (79 / 81)
  - [ ] 10.2 Point, line and edge detection (701 / 703)

## Reading order

1. 2.5 and 2.6
2. 3.4

## Open questions

- Disjoint sets (10.1 condition c): explained with the crayon-colouring analogy. Confirm next session.

## Log

- 2026-11-06: 10.1 read; 3.4 started.
```

Rules:

- `- [ ]` is not yet. `- [x]` is done. In-progress detail goes in free text after the colon. There are no other checkbox states.
- Indentation of two spaces means "read first". Depth is unlimited. Three levels is usually enough.
- Page references in parentheses are `printed / PDF` when a textbook is the source. Lecture references are `L7B` or a `lectures/<name>.lecture/` path when a Recording is the source.
- Section order is fixed: title line, Goal / Source / Updated lines, Tree, Reading order, Open questions, Log. `pps modules add` writes this skeleton with those sections empty.
- After an edit, update `Updated:` and append a Log line, then sync.

The tree is the student's prerequisite map. Nodes are things the student needs, with where to read them. It is not a copy of a syllabus, a textbook, or slides.

### Showing and editing

These phrases all mean the same thing: resolve the module, print `knowledge-tree.md`, and stop. Do not summarize or rewrite the tree when asked to show it.

- "show the 4704 knowledge tree"
- "4704 tree", "4704 plan", "the image module map"
- "what do I need to know for 4704"
- `/module 4704`, `/module show img analysis`

The noun may be tree, plan, map, list, or prerequisites. The verb may be show, print, give me, or what is. The module reference follows Resolving a mention.

`pps modules show <mention>` resolves the mention, then prints the folder path and the file. Exit 3, with the candidate list, when the mention does not resolve.

Editing phrases ("add X to the 4704 tree", "mark 3.4 done", "I understood convolution") edit the file in place, update the checkbox or node, append a Log line, print the changed node, and sync.

## `pps modules`

Work from the repository root. The skills already run there. The modules root defaults to `./modules` relative to the working directory.

Override order, the same pattern as the lecture directory: `--modules-dir`, an explicit `--config`, `PODLEPARSESSKEWL_MODULES_DIR`, the `modules_dir` key in a discovered `podleparsesskewl.toml`, then the default. The override is for an unusual layout. The standard setup is the nested clone at `./modules`.

### Subcommands

| Command | Does | Exit |
| --- | --- | --- |
| `pps modules init <url>` | Clone `<url>` into `modules/` when absent; verify the remote and the layout; print the doctor Modules block. No-op when `modules/` is already that clone. | 0. 2 when `modules/` exists and is not a clone of that remote. |
| `pps modules sync` | Pull with rebase and autostash, regenerate `MODULES.md`, commit when dirty, push. One summary line. | 0. 1 on a rebase conflict or an autostash re-apply conflict (the line names the files). Pull failures other than a conflict, and push failures, are warnings. |
| `pps modules list [--json]` | Table of code, title, folder, status, alias count, and tree checkbox counts (done/total). | 0 |
| `pps modules resolve <mention...> [--json]` | Resolve as below. JSON, or one human line without `--json`. | 0 resolved. 3 for suggest, ambiguous, or unknown. 2 on error. |
| `pps modules show <mention...>` | Resolve, then print the folder path and `knowledge-tree.md`. | 0. 3 when unresolved. |
| `pps modules add <CODE> --title "<title>" --short "<short>" [--alias <a>]... [--status active]` | Validate, create the folder, `module.json`, the tree skeleton, `work/`, and `material/`, regenerate the table, then sync. | 0. 2 on a validation error or an existing code. |
| `pps modules alias <CODE> "<alias>"` | Normalize, validate, append, regenerate the table, then sync. | 0. 2 when the alias collides. |
| `pps modules check` | Clone present and has a remote; folder names match manifests; codes and aliases are unique; every module has a tree; `MODULES.md` equals a fresh generation. Prints each problem. | 0 when clean. 1 when there are problems. |

`add` ends with sync. `alias` ends with sync. Both refuse an alias that already resolves to another module, a bare code or number, or a string shorter than three characters.

`doctor` prints a Modules block and does not change its own exit code because of that block. The block reports the modules root and which setting supplied it, clone status (`clone ok (origin ...)`, `not a clone`, or `missing: run pps modules init <url>`), the module count, dirty / ahead / behind, and the `check` result. `git` is reported next to ffmpeg and ffprobe.

A machine with no `modules/` directory gets a message from `pps modules show` that names `pps modules init` and this file.

### Resolving a mention

`pps modules resolve` decides in this order. The first step that decides wins. Steps after the bands are the `/module` skill, not the command.

1. Normalize: lower case, replace punctuation with spaces, collapse whitespace, drop stop words (`the`, `a`, `an`, `module`, `mod`, `course`, `class`, `one`, `for`, `and`, `of`, `to`, `in`, `on`).
2. Code. The pattern is `\b([a-z]{2,3})?(\d{4})([a-z])?\b`. With letters, the code must match ignoring case. Digits only match any code whose digit block equals them. One hit resolves (`matched_by` `code` or `number`). Two hits are `ambiguous` and keep `matched_by` `code` or `number`.
3. Near-code. A four-digit block that matched nothing, and is within one digit of exactly one registered code, is `suggest` with `matched_by` `near-code`. `4714` against only `EE4704` is this case. When two registered codes are that close, the result is `ambiguous` and keeps `matched_by` `near-code`. A near-code is never auto-resolved and never stored as an alias.
4. Alias. The normalized mention equals a normalized alias of exactly one module. Resolved, `matched_by` `alias`.
5. Fuzzy. Score every module. `best >= 0.85` and `best - second >= 0.15` resolves (`matched_by` `fuzzy`). `best >= 0.60` with that same gap is `suggest` with that one candidate. `best >= 0.60` with a smaller gap is `ambiguous`, listing every candidate at or above 0.60. Otherwise the result is `unknown`, and the candidates are the top three. A tie is always `ambiguous` (or `unknown` below 0.60). Candidates are listed by score, with ties ordered `status: active` first, then the lower code; that order never resolves or suggests a winner.

Thresholds are `RESOLVE_SCORE = 0.85`, `SUGGEST_SCORE = 0.60`, and `MIN_GAP = 0.15`.

JSON shape:

```json
{
  "status": "resolved",
  "mention": "img analysis",
  "module": {"code": "EE4704", "title": "Image Processing and Analysis", "folder": "modules/EE4704 - Image Processing"},
  "matched_by": "alias",
  "score": 1.0,
  "candidates": []
}
```

`module` is present for `resolved` and `suggest` only. `status` is `resolved`, `suggest`, `ambiguous`, or `unknown`. `matched_by` is `code`, `number`, `alias`, `fuzzy`, or `near-code`. `score` is the match score from the step that decided.

A code, bare number, or alias that is already visible in `MODULES.md` may be resolved in place, without the command. Anything else calls `pps modules resolve`.

On `suggest`, `ambiguous`, or `unknown`, ask one short question. Examples: "Taking 'chip design' as EE5518 VLSI, ok?" and "'signal processing' is not a module I know. New module? Give me the code." On a yes for an existing module, run `pps modules alias <CODE> "<mention>"`, unless the mention is a code, bare number, or digit near-miss such as `4714`; those are never stored as aliases, including when they came back `ambiguous`. On a correction, persist the alias on the module the correction named. On a new module, propose `<CODE> - <Short>` with the naming rule above and, on a yes, run `pps modules add`.

Say which module was taken, in one short line, when `matched_by` is `fuzzy` or the mention was resolved by that question. Stay silent on a code, number, or alias hit.

Do not persist a mention that fuzzy matching already resolved. Do not persist a digit near-miss.
