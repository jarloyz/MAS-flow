from __future__ import annotations

import argparse
import contextlib
import io
import shlex
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import masflow  # noqa: E402
import related_tests as rt  # noqa: E402

ENTERPRISE = {
    "name": "ent",
    "path": "ent",
    "tests": {"file": "cd {workspace}/mudrais && ./vendor/bin/sail test /var/www/mudrais-enterprise/tests/{file}"},
    "checks": ["cd {project} && sail phpstan analyse --level=5 <slice PHP files>"],
}
CORE = {"name": "core", "path": "core", "tests": {"file": "cd {project} && sail test {file}"}}


def expand(text: str) -> str:
    return text.replace("{workspace}", "/ws").replace("{project}", "/ws/proj")


def make_repo(files: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp())
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def stub_runner(outputs: dict[str, str]):
    def run(args: list[str]) -> str:
        key = " ".join(a for a in args if a != "-z")
        return outputs.get(key, "").replace("\n", "\0")
    return run


class MapTestsTest(unittest.TestCase):
    def test_path_convention(self) -> None:
        tests = ["tests/Unit/FooServiceTest.php", "tests/Unit/OtherTest.php"]
        result = rt.map_tests(["src/Foo/FooService.php"], tests, lambda p: "")
        self.assertEqual(["tests/Unit/FooServiceTest.php"], result)

    def test_class_reference_mapping(self) -> None:
        tests = ["tests/Feature/CheckoutTest.php", "tests/Feature/OtherTest.php"]
        contents = {tests[0]: "use App\\FooService; new FooService();", tests[1]: "FooServiceExtra only"}
        result = rt.map_tests(["src/FooService.php"], tests, lambda p: contents[p])
        self.assertEqual(["tests/Feature/CheckoutTest.php"], result)

    def test_changed_test_file_passthrough(self) -> None:
        changed = ["tests/Unit/AloneTest.php", "apps/shop/tests/x.test.js", "README.md"]
        result = rt.map_tests(changed, [], lambda p: "")
        self.assertEqual(["apps/shop/tests/x.test.js", "tests/Unit/AloneTest.php"], result)

    def test_js_mapping(self) -> None:
        tests = ["apps/shop/tests/cart.test.js", "apps/shop/tests/other.test.js"]
        changed = ["apps/shop/extensions/theme/assets/cart.js", "apps/shop/extensions/theme/assets/missing.js"]
        self.assertEqual(["apps/shop/tests/cart.test.js"], rt.map_tests(changed, tests, lambda p: ""))

    def test_dedup_and_sorted(self) -> None:
        tests = ["tests/BTest.php", "tests/ATest.php"]
        result = rt.map_tests(["src/A.php", "src/A.php", "tests/ATest.php", "src/B.php"], tests, lambda p: "")
        self.assertEqual(["tests/ATest.php", "tests/BTest.php"], result)


class ChangedFilesTest(unittest.TestCase):
    def test_union_of_all_sources(self) -> None:
        runner = stub_runner({
            "diff --name-only origin/main...HEAD": "a.php\nb.php\n",
            "diff --name-only": "b.php\nc.php\n",
            "diff --name-only --cached": "d.php\n",
            "ls-files --others --exclude-standard": "e.php\n",
        })
        self.assertEqual((["a.php", "b.php", "c.php", "d.php", "e.php"], True), rt.changed_files(Path("."), "origin/main", runner))

    def test_unknown_base_falls_back_to_working_tree(self) -> None:
        def run(args: list[str]) -> str:
            if args[-1].endswith("...HEAD"):
                raise rt.GitError("bad ref")
            return "w.php\0" if args == ["diff", "--name-only", "-z"] else ""
        self.assertEqual((["w.php"], False), rt.changed_files(Path("."), "nope", run))

    def test_nul_split_keeps_exact_names(self) -> None:
        runner = lambda args: "tests/a b é.php\0" if args[:2] == ["diff", "--name-only"] and len(args) == 3 else ""
        files, _ = rt.changed_files(Path("."), "origin/main", runner)
        self.assertEqual(["tests/a b é.php"], files)

    def test_base_starting_with_dash_rejected(self) -> None:
        with self.assertRaises(ValueError):
            rt.changed_files(Path("."), "--output=x", stub_runner({}))

    def test_filter_only(self) -> None:
        changed = ["src/A.php", "src/sub/B.php", "srcx/C.php", "tests/ATest.php"]
        self.assertEqual(["src/A.php", "src/sub/B.php"], rt.filter_only(changed, ["src"]))
        self.assertEqual(["tests/ATest.php"], rt.filter_only(changed, ["tests/ATest.php"]))
        self.assertEqual(changed, rt.filter_only(changed, None))
        self.assertEqual([], rt.filter_only(changed, []))

    def test_normalize_only_absolute_relative_and_outside(self) -> None:
        repo = make_repo({})
        normalized, ignored = rt.normalize_only(
            repo, [str(repo / "src/A.php"), "./src/B.php", "src//C.php", "../escape.php", "/etc/passwd"]
        )
        self.assertEqual(["src/A.php", "src/B.php", "src/C.php"], normalized)
        self.assertEqual(["../escape.php", "/etc/passwd"], ignored)

    def test_related_with_absolute_only_maps_js_and_passthrough(self) -> None:
        app = "apps/shop"
        repo = make_repo({
            f"{app}/tests/results-page.test.js": "x",
            f"{app}/extensions/theme/assets/results-page.js": "y",
        })
        runner = stub_runner({"diff --name-only": f"{app}/extensions/theme/assets/results-page.js\n{app}/extensions/theme/assets/results-page.css\n"})
        only, _ = rt.normalize_only(repo, [
            str(repo / app / "extensions/theme/assets/results-page.js"),
            str(repo / app / "extensions/theme/assets/results-page.css"),
            str(repo / app / "tests/results-page.test.js"),
        ])
        result, _ = rt.related(ENTERPRISE, repo, expand, "origin/main", runner=runner, only=only)
        self.assertEqual([f"{app}/tests/results-page.test.js"], result["tests"])
        self.assertIn(f"{app}/tests/results-page.test.js", result["files_changed"])

    def test_explicit_unchanged_test_file_included(self) -> None:
        repo = make_repo({"tests/KeepTest.php": "x"})
        result, _ = rt.related(CORE, repo, expand, "origin/main", runner=stub_runner({}), only=["tests/KeepTest.php"])
        self.assertEqual(["tests/KeepTest.php"], result["tests"])

    def test_only_all_outside_repo_yields_nothing(self) -> None:
        repo = make_repo({"tests/KeepTest.php": "x"})
        runner = stub_runner({"diff --name-only": "src/Keep.php\n"})
        only, ignored = rt.normalize_only(repo, ["/etc/passwd"])
        result, _ = rt.related(CORE, repo, expand, "origin/main", runner=runner, only=only)
        self.assertEqual(1, len(ignored))
        self.assertEqual([], result["tests"])


class CommandsTest(unittest.TestCase):
    def test_php_command_strips_tests_prefix_and_combines(self) -> None:
        cmds = rt.build_commands(ENTERPRISE, expand, ["tests/A/ATest.php", "tests/BTest.php"], [])
        self.assertEqual(
            ["cd /ws/mudrais && ./vendor/bin/sail test /var/www/mudrais-enterprise/tests/A/ATest.php /var/www/mudrais-enterprise/tests/BTest.php"],
            cmds,
        )

    def test_core_template_keeps_relative_path(self) -> None:
        cmds = rt.build_commands(CORE, expand, ["tests/ATest.php"], [])
        self.assertEqual(["cd /ws/proj && sail test tests/ATest.php"], cmds)

    def test_jest_fallback_form(self) -> None:
        cmds = rt.build_commands(ENTERPRISE, expand, ["apps/shop/tests/cart.test.js"], [])
        self.assertEqual(
            ["cd /ws/mudrais && ./vendor/bin/sail bash -c 'cd /var/www/mudrais-enterprise/apps/shop && npx jest tests/cart.test.js'"],
            cmds,
        )

    def test_hostile_names_are_quoted(self) -> None:
        hostile = "tests/a;rm -rf x Test.php"
        spaced = "tests/with space Test.php"
        cmd = rt.build_commands(ENTERPRISE, expand, [hostile, spaced], [])[0]
        words = shlex.split(cmd)
        self.assertIn("/var/www/mudrais-enterprise/tests/a;rm -rf x Test.php", words)
        self.assertIn("/var/www/mudrais-enterprise/tests/with space Test.php", words)
        self.assertNotIn("rm", words)

    def test_hostile_js_name_survives_bash_c(self) -> None:
        cmd = rt.build_commands(ENTERPRISE, expand, ["apps/shop/tests/a;rm -rf x.test.js"], [])[0]
        inner = shlex.split(cmd)[-1]
        self.assertEqual(["cd", "/var/www/mudrais-enterprise/apps/shop", "&&", "npx", "jest", "tests/a;rm -rf x.test.js"], shlex.split(inner))

    def test_hostile_phpstan_path_quoted(self) -> None:
        cmd = rt.build_commands(ENTERPRISE, expand, [], ["src/a;rm x.php"])[0]
        self.assertEqual("src/a;rm x.php", shlex.split(cmd)[-1])

    def test_jest_template_override(self) -> None:
        project = {**ENTERPRISE, "tests": {**ENTERPRISE["tests"], "jest": "cd {project}/{app} && jest {files}"}}
        cmds = rt.build_commands(project, expand, ["apps/shop/tests/cart.test.js"], [])
        self.assertEqual(["cd /ws/proj/apps/shop && jest tests/cart.test.js"], cmds)

    def test_phpstan_for_changed_sources_only(self) -> None:
        cmds = rt.build_commands(ENTERPRISE, expand, [], ["src/Foo.php", "tests/FooTest.php", "README.md"])
        self.assertEqual(["cd /ws/proj && sail phpstan analyse --level=5 src/Foo.php"], cmds)


class RelatedTest(unittest.TestCase):
    def test_empty_diff(self) -> None:
        repo = make_repo({"tests/ATest.php": "x"})
        result, code = rt.related(ENTERPRISE, repo, expand, "origin/main", runner=stub_runner({}))
        self.assertEqual(0, code)
        self.assertEqual({"files_changed": [], "tests": [], "commands": [], "base_resolved": True}, result)

    def test_only_restricts_changed_files(self) -> None:
        repo = make_repo({"tests/FooServiceTest.php": "x", "tests/BarTest.php": "x"})
        runner = stub_runner({"diff --name-only": "src/FooService.php\nsrc/Bar.php\n"})
        result, _ = rt.related(CORE, repo, expand, "origin/main", runner=runner, only=["src/Bar.php"])
        self.assertEqual(["src/Bar.php"], result["files_changed"])
        self.assertEqual(["tests/BarTest.php"], result["tests"])

    def test_base_resolved_false_in_json_result(self) -> None:
        def run(args: list[str]) -> str:
            if args[-1].endswith("...HEAD"):
                raise rt.GitError("bad")
            return ""
        result, _ = rt.related(CORE, make_repo({}), expand, "nope", runner=run)
        self.assertFalse(result["base_resolved"])

    def test_cli_rejects_dash_base(self) -> None:
        root = make_repo({"proj/x": "x"})
        ws = masflow.Workspace(root, {"projects": [{"name": "core", "path": "proj", "tests": {"file": "t {file}"}}]})
        args = argparse.Namespace(project="core", base="--output=x", group=None, json=False, only=[])
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
            masflow.cmd_related_tests(ws, args)
        self.assertEqual(2, ctx.exception.code)
        self.assertIn("invalid base", err.getvalue())

    def test_diff_maps_to_tests(self) -> None:
        repo = make_repo({"tests/FooServiceTest.php": "x", "src/FooService.php": "y"})
        runner = stub_runner({"diff --name-only": "src/FooService.php\n"})
        result, code = rt.related(ENTERPRISE, repo, expand, "origin/main", runner=runner)
        self.assertEqual(0, code)
        self.assertEqual(["tests/FooServiceTest.php"], result["tests"])
        self.assertEqual(2, len(result["commands"]))

    def test_group_expansion(self) -> None:
        repo = make_repo({"tests/Cap/ATest.php": "x", "tests/Cap/BTest.php": "x", "tests/Other/CTest.php": "x"})
        project = {**CORE, "test_groups": {"CAP-X-01": ["tests/Cap/*Test.php"]}}
        result, code = rt.related(project, repo, expand, "origin/main", group="CAP-X-01")
        self.assertEqual(0, code)
        self.assertEqual(["tests/Cap/ATest.php", "tests/Cap/BTest.php"], result["tests"])
        self.assertEqual(["cd /ws/proj && sail test tests/Cap/ATest.php tests/Cap/BTest.php"], result["commands"])

    def test_unknown_group_exit_code(self) -> None:
        repo = make_repo({})
        project = {**CORE, "test_groups": {"CAP-X-01": ["tests/*.php"]}}
        result, code = rt.related(project, repo, expand, "origin/main", group="CAP-NOPE")
        self.assertEqual(2, code)
        self.assertEqual(["CAP-X-01"], result["known_groups"])

    def test_cli_unknown_group_exits_2_and_lists_groups(self) -> None:
        root = make_repo({"proj/tests/ATest.php": "x"})
        config = {"projects": [{"name": "core", "path": "proj", "tests": {"file": "t {file}"}, "test_groups": {"CAP-X-01": ["tests/ATest.php"]}}]}
        ws = masflow.Workspace(root, config)
        args = argparse.Namespace(project="core", base="origin/main", group="CAP-NOPE", json=False, only=[])
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
            masflow.cmd_related_tests(ws, args)
        self.assertEqual(2, ctx.exception.code)
        self.assertIn("CAP-X-01", err.getvalue())

    def test_cli_group_prints_command(self) -> None:
        root = make_repo({"proj/tests/ATest.php": "x"})
        config = {"projects": [{"name": "core", "path": "proj", "tests": {"file": "t {file}"}, "test_groups": {"CAP-X-01": ["tests/ATest.php"]}}]}
        args = argparse.Namespace(project="core", base="origin/main", group="CAP-X-01", json=False, only=[])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            masflow.cmd_related_tests(masflow.Workspace(root, config), args)
        self.assertEqual("t tests/ATest.php", out.getvalue().strip())


class ValidateGroupsTest(unittest.TestCase):
    def test_no_groups_is_ok(self) -> None:
        self.assertEqual([], rt.validate_groups(CORE, Path(".")))

    def test_valid_group(self) -> None:
        repo = make_repo({"tests/ATest.php": "x"})
        self.assertEqual([], rt.validate_groups({"name": "p", "test_groups": {"CAP-A": ["tests/*Test.php"]}}, repo))

    def test_bad_path_reported(self) -> None:
        repo = make_repo({"tests/ATest.php": "x"})
        problems = rt.validate_groups({"name": "p", "test_groups": {"CAP-A": ["tests/Missing*.php"]}}, repo)
        self.assertEqual(1, len(problems))
        self.assertIn("CAP-A", problems[0])

    def test_non_list_entry_reported(self) -> None:
        problems = rt.validate_groups({"name": "p", "test_groups": {"CAP-A": "tests/x.php", "CAP-B": [1]}}, Path("."))
        self.assertEqual(2, len(problems))


if __name__ == "__main__":
    unittest.main()
