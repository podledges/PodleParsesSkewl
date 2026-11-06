"""Private module registry, deterministic resolution, and explicit git synchronization."""

from __future__ import annotations

import json
import re
import socket
import subprocess
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from podleparsesskewl.errors import PpsError

# Planning report section 3.3; the cold-start fixture is retained in test_modules.py.
RESOLVE_SCORE = 0.85
SUGGEST_SCORE = 0.60
MIN_GAP = 0.15
CODE = re.compile(r"[A-Z]{2,3}[0-9]{4}[A-Z]?")
CODE_MENTION = re.compile(r"\b([a-z]{2,3})?([0-9]{4})([a-z])?\b", re.I)
SHORT = re.compile(r"[A-Za-z0-9 &+\-]{1,32}")
STOP_WORDS = frozenset("the a an module mod course class one for and of to in on".split())
STATUSES = ("active", "paused", "done")
IGNORE_RULES = ("*/material/", "*/lectures/", ".DS_Store")


@dataclass(frozen=True)
class Module:
    code: str
    title: str
    short: str
    aliases: tuple[str, ...]
    status: str
    added: str
    folder: Path

    def manifest(self) -> dict:
        result = asdict(self)
        del result["folder"]
        return result


@dataclass(frozen=True)
class SyncResult:
    summary: str
    warnings: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()

    @property
    def exit_code(self) -> int:
        return 1 if self.conflicts else 0


def normalize(mention: str) -> str:
    return " ".join(word for word in re.sub(r"[^\w]+|_", " ", mention.lower()).split()
                    if word not in STOP_WORDS)


def validate_code(code: str) -> None:
    if not isinstance(code, str) or CODE.fullmatch(code) is None:
        raise PpsError("module code must match EE4704, CG2271 or CS1010S (uppercase)")


def validate_short(short: str) -> None:
    if (not isinstance(short, str) or SHORT.fullmatch(short) is None
            or not short.strip() or short != short.strip()):
        raise PpsError("short name must be 1-32 letters, digits, spaces, &, + or -, without outer spaces")


def derive_folder(code: str, short: str) -> str:
    validate_code(code)
    validate_short(short)
    return f"{code} - {short}"


def _validate_alias(alias: str) -> None:
    if not isinstance(alias, str) or len(alias) < 3 or not normalize(alias):
        raise PpsError("alias must contain at least three normalized characters")
    if alias.isdigit() or CODE_MENTION.fullmatch(alias):
        raise PpsError("an alias cannot be a bare module code or number (including near-codes)")
    if alias != normalize(alias):
        raise PpsError(f"alias is not normalized: {alias!r}")


def _read_module(folder: Path) -> Module:
    path = folder / "module.json"
    if folder.is_symlink() or path.is_symlink():
        raise PpsError(f"module folders and manifests cannot be symlinks: {folder}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("manifest must be an object")
        for key in ("code", "title", "short", "status", "added"):
            if not isinstance(payload.get(key), str) or not payload[key].strip():
                raise ValueError(f"{key} must be a non-empty string")
        if not isinstance(payload.get("aliases"), list):
            raise ValueError("aliases must be a list")
        validate_code(payload["code"])
        validate_short(payload["short"])
        if payload["status"] not in STATUSES:
            raise ValueError("status must be active, paused or done")
        date.fromisoformat(payload["added"])
        for alias in payload["aliases"]:
            _validate_alias(alias)
        module = Module(**{key: payload[key] for key in ("code", "title", "short", "status", "added")},
                        aliases=tuple(payload["aliases"]), folder=folder)
        if folder.name != derive_folder(module.code, module.short):
            raise ValueError("folder name does not match manifest code and short")
        return module
    except (OSError, ValueError, TypeError, PpsError) as exc:
        raise PpsError(f"{path}: {exc}") from exc


def _scan(root: Path) -> tuple[list[Module], list[str]]:
    if not root.is_dir():
        raise PpsError(f"missing modules folder: {root}; run pps modules init <url> (docs/modules.md)")
    modules: list[Module] = []
    problems: list[str] = []
    codes: set[str] = set()
    aliases: dict[str, str] = {}
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or folder.name.startswith(("_", ".")):
            continue
        # Also diagnose renamed modules rather than silently losing their manifests.
        if not (folder / "module.json").exists() and " - " not in folder.name:
            continue
        try:
            module = _read_module(folder)
            if module.code in codes:
                problems.append(f"duplicate module code: {module.code}")
            codes.add(module.code)
            for alias in module.aliases:
                if alias in aliases:
                    problems.append(f"duplicate alias {alias!r}: {aliases[alias]}, {module.code}")
                aliases[alias] = module.code
            modules.append(module)
        except PpsError as exc:
            problems.append(str(exc))
    return sorted(modules, key=lambda item: item.code), problems


def load_modules(root: Path) -> list[Module]:
    modules, problems = _scan(root)
    if problems:
        raise PpsError("\n".join(problems))
    return modules


def score(mention: str, module: Module) -> float:
    query = normalize(mention).split()
    tokens = normalize(" ".join((module.code, re.search(r"\d{4}", module.code)[0],
                                 module.title, module.short, *module.aliases))).split()
    if not query:
        return 0.0

    def similarity(left: str, right: str) -> float:
        ratio = SequenceMatcher(None, left, right).ratio()
        if min(len(left), len(right)) >= 3 and (left.startswith(right) or right.startswith(left)):
            ratio = max(ratio, 0.9)
        return ratio

    return sum(max(similarity(word, token) for token in tokens) for word in query) / len(query)


def _rank(modules: list[Module], mention: str) -> list[tuple[Module, float]]:
    return sorted(((module, score(mention, module)) for module in modules),
                  key=lambda pair: (-pair[1], pair[0].status != "active", pair[0].code))


def resolve(mention: str, modules: list[Module]) -> dict:
    def result(status: str, by: str, ranked: list[tuple[Module, float]]) -> dict:
        output = {"status": status, "mention": mention, "matched_by": by,
                  "score": round(ranked[0][1], 4) if ranked else 0.0,
                  "candidates": [{"code": module.code, "score": round(value, 4)}
                                 for module, value in ranked]}
        if status in ("resolved", "suggest"):
            module = ranked[0][0]
            output["module"] = {"code": module.code, "title": module.title, "folder": str(module.folder)}
        return output

    matches = list(CODE_MENTION.finditer(mention))
    hits: dict[str, Module] = {}
    for match in matches:
        for module in modules:
            if ((match[1] or match[3]) and module.code.lower() == match[0].lower()
                    or not (match[1] or match[3]) and match[2] == re.search(r"\d{4}", module.code)[0]):
                hits[module.code] = module
    if hits:
        ranked = [(module, 1.0) for module in sorted(hits.values(), key=lambda m: (m.status != "active", m.code))]
        return result("resolved" if len(hits) == 1 else "ambiguous",
                      "code" if any(m[1] or m[3] for m in matches) else "number", ranked)
    near = [module for module in modules if any(
        sum(a != b for a, b in zip(match[2], re.search(r"\d{4}", module.code)[0])) == 1
        for match in matches)]
    if near:
        return result("suggest" if len(near) == 1 else "ambiguous", "near-code",
                      [(m, 0.75) for m in sorted(near, key=lambda m: (m.status != "active", m.code))])
    normalized = normalize(mention)
    aliases = [module for module in modules if normalized in module.aliases]
    if aliases:
        return result("resolved" if len(aliases) == 1 else "ambiguous", "alias", [(m, 1.0) for m in aliases])
    ranked = _rank(modules, mention)
    best = ranked[0][1] if ranked else 0.0
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    # Unknown explicit codes must never silently become a different course via fuzzy tokens.
    if matches:
        return result("unknown", "fuzzy", ranked[:3])
    if best >= SUGGEST_SCORE:
        if best - second + 1e-12 >= MIN_GAP:
            return result("resolved" if best >= RESOLVE_SCORE else "suggest", "fuzzy", ranked[:3])
        return result("ambiguous", "fuzzy", [pair for pair in ranked if pair[1] >= SUGGEST_SCORE])
    return result("unknown", "fuzzy", ranked[:3])


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def render_table(modules: list[Module]) -> str:
    lines = ["<!-- generated by `pps modules sync` from */module.json; edit the manifests, not this table -->",
             "# Modules", "", "| Code | Module | Folder | Status | Aliases |",
             "| --- | --- | --- | --- | --- |"]
    for module in sorted(modules, key=lambda m: m.code):
        values = (module.code, module.title, f"`{module.folder.name}/`", module.status, ", ".join(module.aliases))
        lines.append("| " + " | ".join(_cell(value) for value in values) + " |")
    return "\n".join(lines) + "\n"


def _write(path: Path, content: str) -> None:
    if path.is_symlink():
        raise PpsError(f"refusing to write a symlink: {path}")
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8")


def write_table(root: Path, modules: list[Module]) -> None:
    _write(root / "MODULES.md", render_table(modules))


def tree_skeleton(code: str, title: str, today: str) -> str:
    return (f"# {code} - {title}: knowledge tree\n\nGoal: \nSource: \nUpdated: {today}\n\n"
            "## Tree\n\n## Reading order\n\n## Open questions\n\n## Log\n")


def _save_manifest(module: Module) -> None:
    _write(module.folder / "module.json", json.dumps(module.manifest(), indent=2, ensure_ascii=False) + "\n")


def _alias_available(alias: str, code: str, modules: list[Module]) -> None:
    _validate_alias(alias)
    if any(alias in m.aliases and m.code != code for m in modules):
        raise PpsError(f"alias {alias!r} already belongs to another module")
    resolution = resolve(alias, modules)
    if resolution["status"] == "resolved" and resolution["module"]["code"] != code:
        raise PpsError(f"alias {alias!r} already resolves to {resolution['module']['code']}")


def add_module(root: Path, code: str, title: str, short: str, aliases: tuple[str, ...] = (),
               status: str = "active", added: str | None = None) -> Module:
    name = derive_folder(code, short)
    if not title.strip() or "\n" in title or "\r" in title:
        raise PpsError("title must be a non-empty single line")
    if status not in STATUSES:
        raise PpsError("status must be active, paused or done")
    modules = load_modules(root)
    if any(module.code == code for module in modules) or (root / name).exists():
        raise PpsError(f"module already exists: {code}")
    normalized = tuple(dict.fromkeys(normalize(alias) for alias in aliases))
    for alias in normalized:
        _alias_available(alias, code, modules)
    today = added or date.today().isoformat()
    date.fromisoformat(today)
    module = Module(code, title, short, normalized, status, today, root / name)
    module.folder.mkdir()
    _save_manifest(module)
    _write(module.folder / "knowledge-tree.md", tree_skeleton(code, title, today))
    (module.folder / "work").mkdir()
    (module.folder / "work" / ".gitkeep").touch()
    (module.folder / "material").mkdir()
    write_table(root, [*modules, module])
    return module


def add_alias(root: Path, code: str, alias: str) -> Module:
    validate_code(code)
    modules = load_modules(root)
    module = next((m for m in modules if m.code == code), None)
    if module is None:
        raise PpsError(f"unknown module code: {code}")
    alias = normalize(alias)
    _alias_available(alias, code, modules)
    if alias not in module.aliases:
        module = Module(module.code, module.title, module.short, (*module.aliases, alias),
                        module.status, module.added, module.folder)
        _save_manifest(module)
    write_table(root, load_modules(root))
    return module


def _git(root: Path, *args: str, required: bool = True) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                                timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PpsError(f"git: {exc}") from exc
    if required and result.returncode:
        raise PpsError(f"git {' '.join(args)}: {result.stderr.strip() or result.stdout.strip()}")
    return result


def require_clone(root: Path) -> str:
    if not (root / ".git").exists():
        raise PpsError(f"{root}: missing or not a clone; run pps modules init <url> (docs/modules.md)")
    top = _git(root, "rev-parse", "--show-toplevel").stdout.strip()
    if Path(top).resolve() != root.resolve():
        raise PpsError(f"{root}: not a standalone modules clone")
    return _git(root, "remote", "get-url", "origin").stdout.strip()


def _conflicts(root: Path) -> tuple[str, ...]:
    return tuple(_git(root, "diff", "--name-only", "--diff-filter=U").stdout.splitlines())


def _in_rebase(root: Path) -> bool:
    for name in ("rebase-merge", "rebase-apply"):
        path = _git(root, "rev-parse", "--git-path", name).stdout.strip()
        if (root / path).exists():
            return True
    return False


def _privacy_problems(root: Path) -> list[str]:
    tracked = _git(root, "ls-files", "-z").stdout.split("\0")
    return [f"received material must not be tracked: {path}" for path in tracked
            if {"material", "lectures"}.intersection(Path(path).parts[:-1])]


def _ensure_ignores(root: Path) -> None:
    path = root / ".gitignore"
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    missing = [rule for rule in IGNORE_RULES if rule not in content.splitlines()]
    if missing:
        _write(path, content.rstrip("\n") + ("\n" if content else "") + "\n".join(missing) + "\n")


def check(root: Path) -> list[str]:
    problems: list[str] = []
    try:
        require_clone(root)
        problems.extend(_privacy_problems(root))
        conflicts = _conflicts(root)
        problems.extend(f"conflict: {path}" for path in conflicts)
        if _in_rebase(root):
            problems.append("rebase in progress; resolve it before syncing")
    except PpsError as exc:
        problems.append(str(exc))
    try:
        modules, invalid = _scan(root)
        problems.extend(invalid)
        for module in modules:
            tree = module.folder / "knowledge-tree.md"
            if not tree.is_file() or tree.is_symlink():
                problems.append(f"missing or unsafe tree: {tree}")
        table = root / "MODULES.md"
        if not table.is_file() or table.read_text(encoding="utf-8") != render_table(modules):
            problems.append(f"stale MODULES.md: run pps modules sync ({root})")
    except (PpsError, OSError, UnicodeError) as exc:
        problems.append(str(exc))
    return problems


def git_init(root: Path, url: str) -> None:
    if root.exists():
        if require_clone(root) != url:
            raise PpsError(f"{root}: existing clone has a different origin")
    else:
        root.parent.mkdir(parents=True, exist_ok=True)
        _git(root.parent, "clone", "--", url, str(root.resolve()))
    # Empty remotes are valid for first-time setup. Never overwrite an existing registry.
    load_modules(root)
    _ensure_ignores(root)
    project = root / "_project"
    if not project.exists():
        project.mkdir()
        (project / ".gitkeep").touch()
    if not (root / "MODULES.md").exists():
        write_table(root, load_modules(root))
    problems = check(root)
    if problems:
        raise PpsError("\n".join(problems))


def git_sync(root: Path, hostname: str | None = None, now: datetime | None = None) -> SyncResult:
    require_clone(root)
    conflicts = _conflicts(root)
    if conflicts or _in_rebase(root):
        return SyncResult("Modules   conflict; resolve files and continue/abort the rebase before syncing",
                          conflicts=conflicts or ("rebase in progress",))
    privacy = _privacy_problems(root)
    if privacy:
        raise PpsError("\n".join(privacy))
    warnings: list[str] = []
    before = _git(root, "rev-parse", "--verify", "HEAD", required=False).stdout.strip()
    try:
        pull = _git(root, "pull", "--rebase", "--autostash", "--quiet", required=False)
        pull_error = pull.stderr.strip() if pull.returncode else ""
    except PpsError as exc:
        pull_error = str(exc)
    conflicts = _conflicts(root)
    if conflicts or _in_rebase(root):
        return SyncResult("Modules   conflict; resolve files, then continue the rebase (or stage autostash resolutions)",
                          conflicts=conflicts or ("rebase in progress",))
    if pull_error:
        warnings.append(f"pull failed (offline, using local copy): {pull_error}")
    # A remote can introduce unsafe tracked files too. Never push them onward.
    privacy = _privacy_problems(root)
    if privacy:
        raise PpsError("\n".join(privacy))
    _ensure_ignores(root)
    write_table(root, load_modules(root))
    problems = check(root)
    if problems:
        raise PpsError("\n".join(problems))
    after = _git(root, "rev-parse", "--verify", "HEAD", required=False).stdout.strip()
    pulled = 0
    if before and after and before != after:
        pulled = int(_git(root, "rev-list", "--count", f"{before}..{after}").stdout.strip())
    if _git(root, "status", "--porcelain").stdout:
        _git(root, "add", "-A")
        # Nested ignore overrides can defeat root rules. Recheck the staged index
        # before making a commit, not just the files tracked before staging.
        privacy = _privacy_problems(root)
        if privacy:
            raise PpsError("\n".join(privacy))
        stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        _git(root, "commit", "-m", f"study: {stamp} {hostname or socket.gethostname()}")
    counts = _git(root, "rev-list", "--count", "@{upstream}..HEAD", required=False)
    pushed = int(counts.stdout.strip()) if counts.returncode == 0 else 0
    try:
        push = _git(root, "push", "--quiet", required=False)
        push_error = push.stderr.strip() if push.returncode else ""
    except PpsError as exc:
        push_error = str(exc)
    if push_error:
        warnings.append(f"push failed; commits kept locally for next sync: {push_error}")
        pushed = 0
    summary = f"pulled {pulled}, pushed {pushed}" if pulled or pushed else "up to date"
    if warnings:
        summary = "local copy ready; sync incomplete"
    return SyncResult(f"Modules   {summary}", tuple(warnings))


def list_records(modules: list[Module]) -> list[dict]:
    records = []
    for module in modules:
        tree = module.folder / "knowledge-tree.md"
        if tree.is_symlink():
            raise PpsError(f"unsafe tree: {tree}")
        text = tree.read_text(encoding="utf-8")
        boxes = re.findall(r"^ *- \[([ x])\] ", text, re.M)
        records.append({**module.manifest(), "folder": str(module.folder),
                        "alias_count": len(module.aliases), "done": boxes.count("x"), "total": len(boxes)})
    return records


def format_doctor(root: Path, source: str) -> str:
    lines = ["Modules", f"  path         {root}", f"  source       {source}"]
    try:
        origin = require_clone(root)
        lines.append(f"  clone        clone ok (origin {origin})")
        lines.append(f"  dirty        {'yes' if _git(root, 'status', '--porcelain').stdout else 'no'}")
        counts = _git(root, "rev-list", "--left-right", "--count", "HEAD...@{upstream}", required=False)
        ahead, behind = counts.stdout.split() if counts.returncode == 0 else ("unknown", "unknown")
        lines.extend((f"  ahead        {ahead}", f"  behind       {behind} (last fetch)"))
        modules, _ = _scan(root)
        lines.append(f"  count        {len(modules)}")
    except (PpsError, OSError, UnicodeError) as exc:
        lines.append(f"  clone        {exc}")
    problems = check(root)
    lines.append("  check        " + ("ok" if not problems else "\n               ".join(problems)))
    return "\n".join(lines)
