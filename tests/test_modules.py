"""Module contracts, with two real local clones and no network or third-party packages.

Cold-start fixture from planning report section 3.3 (best, runner-up):
4704/code 1.00/.50; 4714 .75/.50; img analysis .88/.49;
image module 1.00/.67; real time os .89/.44; chip design .68/.60;
digital 1.00/1.00; signal processing .71/.58; networks module .50/.33.
Section 8's MIN_GAP takes precedence over section 13.4's 'chip design'
example: .08 is ambiguous, not suggest, with all five modules present.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from podleparsesskewl import modules as m
from podleparsesskewl.cli import main
from podleparsesskewl.config import load_config
from podleparsesskewl.errors import PpsError

FIXTURE = (
    ("EE4704", "Image Processing and Analysis", "Image Processing"),
    ("CG2271", "Real-Time Operating Systems", "RTOS"),
    ("EE5518", "VLSI Digital Circuit Design", "VLSI"),
    ("CS2040", "Data Structures and Algorithms", "DSA"),
    ("EE2026", "Digital Design", "Digital Design"),
)


def fixture() -> list[m.Module]:
    return [m.Module(code, title, short, (), "active", "2026-11-07", Path("modules") / f"{code} - {short}")
            for code, title, short in FIXTURE]


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.modules = fixture()

    def test_code_and_number(self):
        for mention, by in (("EE4704", "code"), ("ee4704", "code"), ("4704", "number"),
                            ("show the 4704 knowledge tree", "number")):
            with self.subTest(mention=mention):
                result = m.resolve(mention, self.modules)
                self.assertEqual(result["status"], "resolved")
                self.assertEqual(result["module"]["code"], "EE4704")
                self.assertEqual(result["matched_by"], by)

    def test_shared_number_and_multiple_mentions_are_ambiguous(self):
        self.modules.append(replace(self.modules[0], code="CS4704"))
        self.assertEqual(m.resolve("4704", self.modules)["status"], "ambiguous")
        self.assertEqual(m.resolve("4704 and 2271", self.modules)["status"], "ambiguous")
        self.assertEqual(m.resolve("EE4704", self.modules)["status"], "resolved")

    def test_near_code_never_resolves(self):
        result = m.resolve("4714", self.modules)
        self.assertEqual((result["status"], result["matched_by"]), ("suggest", "near-code"))
        self.assertEqual(result["module"]["code"], "EE4704")
        self.modules.append(replace(self.modules[0], code="EE4715"))
        self.assertEqual(m.resolve("4714", self.modules)["status"], "ambiguous")
        self.assertNotEqual(m.resolve("CS4704", fixture())["status"], "resolved")

    def test_normalized_alias(self):
        self.modules[0] = replace(self.modules[0], aliases=("img analysis",))
        for mention in ("img analysis", "Img  Analysis!"):
            self.assertEqual(m.resolve(mention, self.modules)["matched_by"], "alias")

    def test_fuzzy_bands(self):
        for mention, status in (("image module", "resolved"), ("img analysis", "resolved"),
                                ("real time os", "resolved"), ("chip design", "ambiguous"),
                                ("digital", "ambiguous"), ("networks module", "unknown"),
                                ("the module", "unknown"), ("", "unknown")):
            with self.subTest(mention=mention):
                self.assertEqual(m.resolve(mention, self.modules)["status"], status)
        separated = [module for module in self.modules if module.code != "EE2026"]
        self.assertEqual(m.resolve("chip design", separated)["status"], "suggest")
        self.assertEqual(m.resolve("anything", [])["status"], "unknown")

    def test_active_tie_first_without_silently_resolving(self):
        self.modules[-1] = replace(self.modules[-1], status="paused")
        result = m.resolve("digital", self.modules)
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["candidates"][0]["code"], "EE5518")


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def add(self, index=0, **kwargs):
        return m.add_module(self.root, *FIXTURE[index], **kwargs)

    def test_scaffold_and_validation(self):
        module = self.add()
        self.assertEqual(module.folder.name, "EE4704 - Image Processing")
        self.assertTrue((module.folder / "work" / ".gitkeep").is_file())
        self.assertTrue((module.folder / "material").is_dir())
        text = (module.folder / "knowledge-tree.md").read_text()
        for heading in ("Goal:", "Source:", "Updated:", "## Tree", "## Reading order", "## Open questions", "## Log"):
            self.assertIn(heading, text)
        self.assertEqual(m.load_modules(self.root), [module])
        self.assertEqual((self.root / "MODULES.md").read_text(), m.render_table([module]))
        for code, short in (("ee4704", "Image"), ("../EE4704", "Image"), ("EE1234", "a" * 33),
                            ("EE1234", "../oops"), ("EE1234", " ")):
            with self.subTest(code=code, short=short), self.assertRaises(PpsError):
                m.add_module(self.root, code, "Title", short)
        with self.assertRaises(PpsError):
            self.add()

    def test_alias_normalization_and_collisions(self):
        self.add()
        self.add(1)
        updated = m.add_alias(self.root, "EE4704", "Img  Analysis!")
        self.assertEqual(updated.aliases, ("img analysis",))
        m.add_alias(self.root, "EE4704", "IMG analysis")
        self.assertEqual(len(m.load_modules(self.root)[1].aliases), 1)
        for alias in ("4714", "EE4714", "ab", "the", "rtos"):
            with self.subTest(alias=alias), self.assertRaises(PpsError):
                m.add_alias(self.root, "EE4704", alias)
        with self.assertRaises(PpsError):
            m.add_alias(self.root, "CG2271", "img analysis")
        with self.assertRaises(PpsError):
            m.add_module(self.root, "EE1234", "New", "New", ("rtos",))
        self.assertFalse((self.root / "EE1234 - New").exists())

    def test_table_idempotence_nonmodules_and_escaping(self):
        self.add()
        (self.root / "_project").mkdir()
        (self.root / "README.md").write_text("private")
        modules = m.load_modules(self.root)
        path = self.root / "MODULES.md"
        before = path.stat().st_mtime_ns
        m.write_table(self.root, modules)
        self.assertEqual(before, path.stat().st_mtime_ns)
        table = m.render_table([replace(modules[0], title="Image | Processing")])
        self.assertIn(r"Image \| Processing", table)

    def test_malformed_manifests_and_duplicates(self):
        module = self.add()
        path = module.folder / "module.json"
        payload = json.loads(path.read_text())
        for field, value in (("aliases", "bad"), ("status", "unknown"), ("added", "today"),
                             ("aliases", [42]), ("aliases", ["IMAGE!"]), ("code", "ee4704")):
            with self.subTest(field=field, value=value):
                path.write_text(json.dumps({**payload, field: value}))
                with self.assertRaises(PpsError):
                    m.load_modules(self.root)
        path.write_text(json.dumps(payload))
        duplicate = module.folder.with_name("EE4704 - Alternate")
        duplicate.mkdir()
        (duplicate / "module.json").write_text(json.dumps({**payload, "short": "Alternate"}))
        with self.assertRaisesRegex(PpsError, "duplicate module code"):
            m.load_modules(self.root)

    def test_symlink_manifest_and_table_writes_rejected(self):
        module = self.add()
        target = self.root / "outside"
        target.write_text("do not overwrite")
        table = self.root / "MODULES.md"
        table.unlink()
        table.symlink_to(target)
        with self.assertRaises(PpsError):
            m.write_table(self.root, [module])
        self.assertEqual(target.read_text(), "do not overwrite")


@unittest.skipUnless(shutil.which("git"), "git required")
class GitModulesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.env = mock.patch.dict(os.environ, {
            "GIT_AUTHOR_NAME": "Module tests", "GIT_AUTHOR_EMAIL": "modules@example.invalid",
            "GIT_COMMITTER_NAME": "Module tests", "GIT_COMMITTER_EMAIL": "modules@example.invalid",
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.remote = self.base / "private.git"
        git(self.base, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.a = self.base / "A" / "modules"
        m.git_init(self.a, str(self.remote))
        self.module = m.add_module(self.a, *FIXTURE[0])
        self.tree_relative = self.module.folder.relative_to(self.a) / "knowledge-tree.md"
        git(self.a, "add", "-A")
        git(self.a, "commit", "-m", "seed")
        git(self.a, "push", "-u", "origin", "main")
        self.b = self.base / "B" / "modules"
        m.git_init(self.b, str(self.remote))

    def cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["modules", "--modules-dir", str(self.a), *args])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_init_idempotence_and_refusals(self):
        head = git(self.a, "rev-parse", "HEAD")
        m.git_init(self.a, str(self.remote))
        self.assertEqual(git(self.a, "status", "--porcelain"), "")
        self.assertEqual(head, git(self.a, "rev-parse", "HEAD"))
        with self.assertRaises(PpsError):
            m.git_init(self.a, "other-remote")
        folder = self.base / "not-a-clone"
        folder.mkdir()
        with self.assertRaisesRegex(PpsError, "init"):
            m.git_init(folder, str(self.remote))

    def test_check_reports_folder_tree_table_and_duplicates(self):
        self.assertEqual(m.check(self.a), [])
        (self.a / self.tree_relative).unlink()
        (self.a / "MODULES.md").write_text("stale")
        problems = "\n".join(m.check(self.a))
        self.assertIn("missing or unsafe tree", problems)
        self.assertIn("stale MODULES.md", problems)
        self.module.folder.rename(self.a / "EE4704 - Wrong")
        self.assertIn("folder name does not match", "\n".join(m.check(self.a)))

    def test_sync_two_clones_dirty_commit_push_and_noop(self):
        tree_b = self.b / self.tree_relative
        tree_b.write_text(tree_b.read_text() + "\n- [x] Topic learned\n")
        result = m.git_sync(self.b, "test-pc", datetime(2026, 11, 7, 12, 34, tzinfo=timezone.utc))
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.warnings, ())
        self.assertIn("pushed 1", result.summary)
        self.assertEqual(git(self.b, "log", "-1", "--format=%s"), "study: 2026-11-07T12:34Z test-pc")
        result = m.git_sync(self.a)
        self.assertIn("pulled 1", result.summary)
        self.assertEqual((self.a / self.tree_relative).read_text(), tree_b.read_text())
        self.assertEqual(m.git_sync(self.a).summary, "Modules   up to date")
        self.assertEqual(git(self.a, "status", "--porcelain"), "")

    def test_committed_conflict_stops_without_staging_or_pushing(self):
        (self.b / self.tree_relative).write_text("B version\n")
        git(self.b, "add", "-A")
        git(self.b, "commit", "-m", "B concurrent")
        (self.a / self.tree_relative).write_text("A version\n")
        m.git_sync(self.a)
        result = m.git_sync(self.b)
        self.assertEqual(result.exit_code, 1)
        self.assertIn(str(self.tree_relative), result.conflicts)
        self.assertIn("<<<<<<<", (self.b / self.tree_relative).read_text())
        self.assertEqual(m.git_sync(self.b).exit_code, 1)
        git(self.b, "rebase", "--abort")
        self.assertEqual((self.b / self.tree_relative).read_text(), "B version\n")

    def test_autostash_conflict_even_when_git_pull_returns_zero(self):
        (self.b / self.tree_relative).write_text("dirty B version\n")
        (self.a / self.tree_relative).write_text("A version\n")
        m.git_sync(self.a)
        result = m.git_sync(self.b)
        self.assertEqual(result.exit_code, 1)
        self.assertIn(str(self.tree_relative), result.conflicts)
        self.assertIn("dirty B version", (self.b / self.tree_relative).read_text())
        self.assertTrue(git(self.b, "stash", "list"))

    def test_offline_still_commits_and_next_sync_pushes(self):
        git(self.a, "remote", "set-url", "origin", str(self.base / "absent.git"))
        (self.a / self.tree_relative).write_text("offline edit\n")
        result = m.git_sync(self.a)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(len(result.warnings), 2)
        self.assertIn("offline", result.warnings[0])
        self.assertIn("study:", git(self.a, "log", "-1", "--format=%s"))
        self.assertEqual(git(self.a, "status", "--porcelain"), "")
        git(self.a, "remote", "set-url", "origin", str(self.remote))
        self.assertIn("pushed 1", m.git_sync(self.a).summary)

    def test_material_ignored_work_synced_and_forced_material_rejected(self):
        material = self.module.folder / "material" / "textbook.pdf"
        material.write_text("synthetic placeholder, not real course material")
        lectures = self.module.folder / "lectures"
        lectures.mkdir()
        (lectures / "lecture.json").write_text("{}")
        work = self.module.folder / "work" / "assignment.md"
        work.write_text("my solution")
        m.git_sync(self.a)
        tracked = git(self.a, "ls-files")
        self.assertNotIn("textbook.pdf", tracked)
        self.assertNotIn("lecture.json", tracked)
        self.assertIn("assignment.md", tracked)
        git(self.a, "add", "-f", str(material))
        with self.assertRaisesRegex(PpsError, "must not be tracked"):
            m.git_sync(self.a)

    def test_nested_ignore_override_cannot_upload_received_material(self):
        # A nested .gitignore could re-include material despite the root ignore.
        (self.module.folder / ".gitignore").write_text("!material/\n!material/**\n")
        (self.module.folder / "material" / "received.txt").write_text("synthetic fixture")
        before = git(self.a, "rev-parse", "HEAD")
        with self.assertRaisesRegex(PpsError, "must not be tracked"):
            m.git_sync(self.a)
        self.assertEqual(git(self.a, "rev-parse", "HEAD"), before)
        self.assertEqual(git(self.remote, "rev-parse", "main"), before)

    def test_cli_list_show_resolve_exit_paths_and_mutations(self):
        code, text, _ = self.cli("list", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(text)[0]["total"], 0)
        code, text, _ = self.cli("show", "4704")
        self.assertEqual(code, 0)
        self.assertTrue(text.endswith((self.a / self.tree_relative).read_text()))
        code, text, _ = self.cli("resolve", "4714", "--json")
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(text)["matched_by"], "near-code")
        self.assertEqual(self.cli("show", "networks")[0], 3)
        self.assertEqual(self.cli("alias", "EE4704", "Img Analysis!")[0], 0)
        self.assertEqual(self.cli("add", "CG2271", "--title", "Real-Time Operating Systems", "--short", "RTOS")[0], 0)
        self.assertEqual(self.cli("check")[0], 0)
        self.assertEqual(git(self.a, "status", "--porcelain"), "")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = main(["modules", "show", "4704", "--modules-dir", str(self.base / "missing")])
        self.assertEqual(code, 2)
        self.assertIn("pps modules init", stderr.getvalue())

    def test_doctor_modules_does_not_change_exit_status(self):
        from podleparsesskewl.deps import Environment, ToolStatus
        found = ToolStatus("ffmpeg", True, Path("/ffmpeg"), "")
        env = Environment(found, replace(found, name="ffprobe"), replace(found, name="transcriber"))
        for root in (self.a, self.base / "missing"):
            with mock.patch("podleparsesskewl.cli.inspect_environment", return_value=env), contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main(["doctor", "--modules-dir", str(root)]), 0)
            self.assertIn("Modules", out.getvalue())
            self.assertIn("git", out.getvalue())
        text = m.format_doctor(self.a, "flag")
        for phrase in ("clone ok", "count", "ahead", "behind", "dirty", "check", "flag"):
            self.assertIn(phrase, text)


class ConfigAndPrivacyTests(unittest.TestCase):
    def test_modules_root_precedence(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "config.toml"
            path.write_text('modules_dir = "configured"\n')
            with mock.patch.dict(os.environ, {"PODLEPARSESSKEWL_MODULES_DIR": "environment"}), mock.patch("podleparsesskewl.config._find_config", return_value=path):
                self.assertEqual(load_config().modules_dir, Path("environment"))
                self.assertEqual(load_config(config_path=path).modules_dir, Path("configured"))
                self.assertEqual(load_config(config_path=path, modules_dir=Path("flag")).modules_dir_source, "flag")
                path.write_text("")
                self.assertEqual(load_config(config_path=path).modules_dir, Path("modules"))
            path.write_text('modules_dir = "discovered"\n')
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch("podleparsesskewl.config._find_config", return_value=path):
                self.assertEqual(load_config().modules_dir, Path("discovered"))

    @unittest.skipUnless(shutil.which("git"), "git required")
    def test_public_privacy_guard(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(git(root, "ls-files", "--", "modules"), "")
        self.assertIn("modules/", (root / ".gitignore").read_text().splitlines())
        self.assertEqual(git(root, "check-ignore", "--no-index", "modules/private-example/module.json"),
                         "modules/private-example/module.json")


if __name__ == "__main__":
    unittest.main()
