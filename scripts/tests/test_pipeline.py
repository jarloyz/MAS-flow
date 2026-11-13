"""Tests for the deterministic pipeline: state, git lifecycle, checks, verify, stats and the CLI."""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gitops  # noqa: E402
import masflow  # noqa: E402
import runs  # noqa: E402
import state  # noqa: E402
import stats  # noqa: E402

HANDOFF = (masflow.TEMPLATES_DIR / "handoff.md").read_text(encoding="utf-8")
PLAN = """## 3. Technical Plan

**Approach:** short.

### Slices
| # | Title | Project | Layer | Executor | Depends on | Wave | Risk | AC | Status | Branch | Retries |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Model | app | data | executor | — | 1 | low | AC1 | pending | — | 0 |
| 2a | Endpoint | app | http | executor | 1 | 2 | high | AC2 | pending | — | 0 |

### AC Traceability
| AC | Slice | Test(s) |
|---|---|---|
| AC1 | 1 | `XTest::test_a` |
"""


def sh(cwd: Path, *args: str) -> str:
    proc = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def make_repo(root: Path, with_origin: bool = True) -> Path:
    repo = root / "repo"
    repo.mkdir()
    sh(repo, "git", "init", "-q", "-b", "main")
    sh(repo, "git", "config", "user.email", "test@example.com")
    sh(repo, "git", "config", "user.name", "Test")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    sh(repo, "git", "add", "README.md")
    sh(repo, "git", "commit", "-q", "-m", "init")
    if with_origin:
        sh(root, "git", "init", "-q", "--bare", "-b", "main", "origin.git")
        sh(repo, "git", "remote", "add", "origin", str(root / "origin.git"))
        sh(repo, "git", "push", "-q", "-u", "origin", "main")
    return repo


def with_plan(text: str) -> str:
    start = text.index("## 3. Technical Plan")
    end = text.index("## 4. Execution Log")
    return text[:start] + PLAN + "\n" + text[end:]


class StateTest(unittest.TestCase):
    def test_update_front_matter_replaces_quotes_and_keeps_other_keys(self):
        text = state.update_front_matter(HANDOFF, {"story": "HU-7", "title": "Fix: the thing #2", "phase": 4, "next_task": None})
        meta, body = masflow.split_front_matter(text)
        self.assertEqual(meta["story"], "HU-7")
        self.assertEqual(meta["title"], "Fix: the thing #2")
        self.assertEqual(meta["phase"], "4")
        self.assertIsNone(meta["next_task"])
        self.assertEqual(meta["status"], "idle")
        self.assertTrue(body.startswith("# MAS-Flow Handoff"))

    def test_update_front_matter_requires_front_matter(self):
        with self.assertRaises(ValueError):
            state.update_front_matter("# no front matter\n", {"story": "x"})

    def test_append_log_goes_inside_section_4(self):
        text = state.append_log(HANDOFF, "- 2026-01-01 planner success — one")
        text = state.append_log(text, "- 2026-01-01 guard rejected — two")
        log = state.sections(text)["4"]
        self.assertIn("— one\n- 2026-01-01 guard rejected — two", log)
        self.assertNotIn("— one", state.sections(text)["5"])
        self.assertIn("## 5. Open Issues", text)

    def test_log_line_is_truncated_to_the_budget(self):
        line = state.log_line("2026-01-01", "guard", "warnings", "word " * 200, 240)
        self.assertLessEqual(len(line), 240)
        self.assertTrue(line.endswith("…"))

    def test_set_slice_row_updates_cells_by_header(self):
        text, found = state.set_slice_row(with_plan(HANDOFF), "2a", {"Status": "closed", "Retries": 1, "Branch": "masflow/HU-1"})
        self.assertTrue(found)
        rows = {row["#"]: row for row in state.slice_rows(text)}
        self.assertEqual((rows["2a"]["Status"], rows["2a"]["Retries"], rows["2a"]["Branch"]), ("closed", "1", "masflow/HU-1"))
        self.assertEqual(rows["1"]["Status"], "pending")
        self.assertEqual(rows["2a"]["Risk"], "high")
        self.assertFalse(state.set_slice_row(text, "9", {"Status": "closed"})[1])

    def test_slice_rows_ignore_other_tables(self):
        self.assertEqual([row["#"] for row in state.slice_rows(with_plan(HANDOFF))], ["1", "2a"])

    def test_budgets_flag_what_is_too_big(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            big_plan = with_plan(HANDOFF).replace("**Approach:** short.", "**Approach:** " + "x" * 20000)
            (directory / "handoff.md").write_text(state.append_log(big_plan, "- 2026-01-01 guard success — " + "y" * 400), encoding="utf-8")
            (directory / "slices").mkdir()
            (directory / "slices" / "slice-1.md").write_text("z" * 9000, encoding="utf-8")
            (directory / "lessons.md").write_text("## Active Rules\n" + "".join(f"- R{i} rule\n" for i in range(40)) + "\n## Log\n- not a rule\n", encoding="utf-8")
            problems = "\n".join(state.budget_problems(directory, {"budgets": {"story_slices": 1}}))
        for expected in ("handoff §3 Technical Plan", "slices in the story is 2", "slices/slice-1.md", "Execution Log lines exceed",
                         "Active Rules is 40 rules"):
            self.assertIn(expected, problems)

    def test_budgets_are_quiet_on_the_templates(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("handoff.md", "lessons.md"):
                (Path(tmp) / name).write_text((masflow.TEMPLATES_DIR / name).read_text(encoding="utf-8"), encoding="utf-8")
            self.assertEqual(state.budget_problems(Path(tmp), {}), [])

    def test_archive_moves_handoff_and_slices_and_resets(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "handoff.md").write_text("old", encoding="utf-8")
            (directory / "slices").mkdir()
            (directory / "slices" / "slice-1.md").write_text("spec", encoding="utf-8")
            target = state.archive_story(directory, HANDOFF, "HU 9/x")
            self.assertEqual((target / "handoff.md").read_text(encoding="utf-8"), "old")
            self.assertTrue((target / "slices" / "slice-1.md").exists())
            self.assertFalse((directory / "slices").exists())
            self.assertEqual((directory / "handoff.md").read_text(encoding="utf-8"), HANDOFF)
            with self.assertRaises(ValueError):
                state.archive_story(directory, HANDOFF, None)


class GitOpsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_full_story_lifecycle_with_a_remote(self):
        repo = make_repo(self.root)
        branch = "masflow/HU-1"
        self.assertEqual(gitops.create_branch(repo, branch, "main")["status"], "success")
        self.assertEqual(gitops.current_branch(repo), branch)
        (repo / "a.txt").write_text("a\n", encoding="utf-8")
        (repo / "wip.txt").write_text("human wip\n", encoding="utf-8")
        result = gitops.commit_slice(repo, branch, "HU-1", "1", "add a", [str(repo / "a.txt")])
        self.assertEqual(result["status"], "success")
        self.assertIn("wip.txt", result["data"]["pending_changes"])
        self.assertEqual(sh(repo, "git", "show", "--name-only", "--format=%s", "HEAD").splitlines(), ["masflow: HU-1 slice1 — add a", "", "a.txt"])
        self.assertEqual(gitops.push_branch(repo, branch)["status"], "success")
        merged = gitops.merge_story(repo, branch, "main", "HU-1", "Title", validated=True, use_gh=False)
        self.assertEqual(merged["status"], "success", merged)
        self.assertEqual(gitops.current_branch(repo), "main")
        self.assertTrue((repo / "a.txt").exists())
        self.assertFalse(gitops.branch_exists(repo, branch))
        self.assertEqual(sh(repo, "git", "rev-parse", "main"), sh(repo, "git", "rev-parse", "origin/main"))
        self.assertTrue((repo / "wip.txt").exists())

    def test_local_only_repository_merges_without_pushing(self):
        repo = make_repo(self.root, with_origin=False)
        gitops.create_branch(repo, "masflow/HU-2", "main")
        (repo / "b.txt").write_text("b\n", encoding="utf-8")
        gitops.commit_slice(repo, "masflow/HU-2", "HU-2", "1", "add b", ["b.txt"])
        self.assertEqual(gitops.push_branch(repo, "masflow/HU-2")["status"], "warnings")
        self.assertEqual(gitops.merge_story(repo, "masflow/HU-2", "main", "HU-2", "T", validated=True)["status"], "success")
        self.assertIn("feat: HU-2 — T", sh(repo, "git", "log", "--format=%s", "-1"))

    def test_create_branch_stops_on_tracked_changes(self):
        repo = make_repo(self.root, with_origin=False)
        (repo / "README.md").write_text("changed\n", encoding="utf-8")
        result = gitops.create_branch(repo, "masflow/HU-3", "main")
        self.assertEqual(result["status"], "needs_human")
        self.assertEqual(gitops.current_branch(repo), "main")
        self.assertEqual((repo / "README.md").read_text(encoding="utf-8"), "changed\n")

    def test_commit_slice_refuses_wrong_branch_and_empty_commit(self):
        repo = make_repo(self.root, with_origin=False)
        self.assertEqual(gitops.commit_slice(repo, "masflow/HU-4", "HU-4", "1", "x", ["README.md"])["status"], "needs_human")
        gitops.create_branch(repo, "masflow/HU-4", "main")
        self.assertEqual(gitops.commit_slice(repo, "masflow/HU-4", "HU-4", "1", "x", ["README.md"])["status"], "error")

    def test_commit_slice_runs_the_formatter_and_stops_when_it_fails(self):
        repo = make_repo(self.root, with_origin=False)
        gitops.create_branch(repo, "masflow/HU-5", "main")
        (repo / "c.txt").write_text("c\n", encoding="utf-8")
        failed = gitops.commit_slice(repo, "masflow/HU-5", "HU-5", "1", "x", ["c.txt"], lambda name: (False, "syntax error"))
        self.assertEqual(failed["status"], "rejected")

        def formatter(name: str):
            (repo / name).write_text("formatted\n", encoding="utf-8")
            return True, ""
        done = gitops.commit_slice(repo, "masflow/HU-5", "HU-5", "1", "x", ["c.txt"], formatter)
        self.assertEqual((done["status"], done["data"]["formatted"]), ("success", ["c.txt"]))
        self.assertEqual(sh(repo, "git", "show", "HEAD:c.txt"), "formatted")

    def test_merge_needs_validation_a_pushed_branch_and_an_unmoved_main(self):
        repo = make_repo(self.root)
        branch = "masflow/HU-6"
        gitops.create_branch(repo, branch, "main")
        (repo / "d.txt").write_text("d\n", encoding="utf-8")
        gitops.commit_slice(repo, branch, "HU-6", "1", "x", ["d.txt"])
        self.assertEqual(gitops.merge_story(repo, branch, "main", "HU-6", "T")["status"], "needs_human")
        not_pushed = gitops.merge_story(repo, branch, "main", "HU-6", "T", validated=True, use_gh=False)
        self.assertIn("push_branch first", not_pushed["summary"])
        gitops.push_branch(repo, branch)

        other = self.root / "other"
        sh(self.root, "git", "clone", "-q", str(self.root / "origin.git"), "other")
        sh(other, "git", "config", "user.email", "o@example.com")
        sh(other, "git", "config", "user.name", "Other")
        (other / "e.txt").write_text("e\n", encoding="utf-8")
        sh(other, "git", "add", "e.txt")
        sh(other, "git", "commit", "-q", "-m", "someone else")
        sh(other, "git", "push", "-q", "origin", "main")

        moved = gitops.merge_story(repo, branch, "main", "HU-6", "T", validated=True, use_gh=False)
        self.assertEqual(moved["status"], "needs_human")
        self.assertIn("moved", moved["summary"])
        self.assertTrue(gitops.branch_exists(repo, branch))

    def test_rollback_reverts_the_slice_commits(self):
        repo = make_repo(self.root, with_origin=False)
        branch = "masflow/HU-7"
        gitops.create_branch(repo, branch, "main")
        (repo / "f.txt").write_text("f\n", encoding="utf-8")
        commit = gitops.commit_slice(repo, branch, "HU-7", "1", "x", ["f.txt"])["data"]["commit"]
        self.assertEqual(gitops.rollback_slice(repo, branch, [commit])["status"], "success")
        self.assertFalse((repo / "f.txt").exists())


class RunsTest(unittest.TestCase):
    def test_extract_failures_from_common_runners(self):
        output = "\n".join([
            "There were 2 failures:",
            "1) Tests\\Feature\\FooTest::test_it_works",
            "2) Tests\\Unit\\BarTest::test_edge with data set \"empty\" ('')",
            "   \x1b[41;1m FAILED \x1b[0m Tests\\Feature\\BazTest > it does a thing                       QueryException",
            "FAILED tests/test_api.py::test_login - AssertionError: nope",
            "  ● checkout › applies the discount",
            "Tests: 3 failed, 120 passed",
        ])
        self.assertEqual(runs.extract_failures(output), [
            "Tests\\Feature\\BazTest > it does a thing", "Tests\\Feature\\FooTest::test_it_works",
            "Tests\\Unit\\BarTest::test_edge", "checkout › applies the discount", "tests/test_api.py::test_login"])

    def test_junit_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "junit.xml"
            report.write_text('<testsuites><testsuite><testcase classname="A" name="ok"/>'
                              '<testcase classname="A" name="bad"><failure>x</failure></testcase>'
                              '<testcase classname="B" name="boom"><error>y</error></testcase></testsuite></testsuites>', encoding="utf-8")
            self.assertEqual(runs.junit_failures(report), ["A::bad", "B::boom"])
            self.assertIsNone(runs.junit_failures(Path(tmp) / "missing.xml"))

    def test_run_checks_filters_files_and_reports_failures(self):
        calls = []

        def fake(command: str, timeout: int):
            calls.append(command)
            return (1, "error on line 3") if "stan" in command else (0, "")
        project = {"name": "app", "slice_checks": [
            "fmt --test {files}",
            {"run": "stan {files}", "ext": [".php"], "under": ["app/"]},
            {"run": "eslint {files}", "ext": [".js"]},
        ]}
        result = runs.run_checks(project, lambda text: text, ["app/A b.php", "tests/ATest.php"], fake)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(calls, ["fmt --test 'app/A b.php' tests/ATest.php", "stan 'app/A b.php'"])
        self.assertEqual([c["result"] for c in result["data"]["checks"]], ["pass", "fail", "skipped"])

    def test_run_checks_without_configuration_lists_manual_checks(self):
        result = runs.run_checks({"name": "app", "checks": ["lint <files>"]}, lambda text: text, ["a"])
        self.assertEqual((result["status"], result["data"]["not_configured"], result["data"]["manual_checks"]), ("warnings", True, ["lint <files>"]))

    def test_verify_project_compares_with_the_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = {"name": "app", "tests": {"full": "run"}}
            output = "1) FooTest::test_old\n2) FooTest::test_new\n"
            red = runs.verify_project(project, lambda t: t, ["FooTest::test_old", "FooTest::test_gone"], Path(tmp) / "app.log", lambda c, t: (1, output))
            self.assertEqual((red["result"], red["regressions"], red["baseline_fixed"]), ("red", ["FooTest::test_new"], ["FooTest::test_gone"]))
            self.assertEqual((Path(tmp) / "app.log").read_text(encoding="utf-8"), output)
            green = runs.verify_project(project, lambda t: t, ["FooTest::test_old", "FooTest::test_new"], Path(tmp) / "app.log", lambda c, t: (1, output))
            self.assertEqual(green["result"], "green")
            unreadable = runs.verify_project(project, lambda t: t, [], Path(tmp) / "app.log", lambda c, t: (2, "Segmentation fault"))
            self.assertEqual(unreadable["result"], "error")


class StatsTest(unittest.TestCase):
    EVENTS = [
        {"ts": "2026-01-01T10:00:00+00:00", "story": "HU-1", "track": "full", "agent": "planner", "status": "success"},
        {"ts": "2026-01-01T11:00:00+00:00", "story": "HU-1", "agent": "guard", "mode": "code_audit", "status": "rejected", "slice": "1"},
        {"ts": "2026-01-01T11:30:00+00:00", "story": "HU-1", "agent": "guard", "mode": "code_audit", "status": "success", "slice": "1"},
        {"ts": "2026-01-01T12:00:00+00:00", "story": "HU-1", "agent": "orchestrator", "status": "success", "slice": "1", "slice_status": "closed"},
        {"ts": "2026-01-01T12:10:00+00:00", "story": "HU-1", "agent": "masflow", "mode": "commit_slice", "status": "success"},
        {"ts": "2026-01-01T12:30:00+00:00", "story": "HU-1", "agent": "masflow", "mode": "checks", "status": "success"},
    ]

    def test_story_and_gate_stats(self):
        story = stats.story_stats(self.EVENTS)[0]
        self.assertEqual((story["story"], story["track"], story["lead_hours"], story["rejected"], story["slices_closed"]), ("HU-1", "full", 2.5, 1, 1))
        gates = {g["gate"]: g for g in stats.gate_stats(self.EVENTS)}
        self.assertEqual(set(gates), {"guard code_audit", "masflow checks"})
        self.assertEqual((gates["guard code_audit"]["runs"], gates["guard code_audit"]["reject_rate"]), (2, 0.5))

    def test_log_stats_reads_execution_log_lines(self):
        body = "- 2026-01-01 guard:code_audit rejected — x\n- 2026-01-01 planner success — y\n- 2026-01-01 10:00 guard warnings — z\nnot a line\n"
        result = stats.log_stats(body)
        self.assertEqual(result["statuses"], {"rejected": 1, "success": 1, "warnings": 1})
        self.assertEqual(result["agents"]["planner"], 1)

    def test_transcript_stats_excludes_long_pauses(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "session" / "subagents"
            directory.mkdir(parents=True)
            (directory / "agent-1.meta.json").write_text(json.dumps({"agentType": "architect"}), encoding="utf-8")
            lines = [
                {"timestamp": "2026-01-01T10:00:00Z", "type": "user", "message": {"content": "go"}},
                {"timestamp": "2026-01-01T10:02:00Z", "type": "assistant", "message": {"id": "m1", "usage": {"input_tokens": 100, "cache_read_input_tokens": 900, "output_tokens": 50}}},
                {"timestamp": "2026-01-01T10:02:00Z", "type": "assistant", "message": {"id": "m1", "usage": {"input_tokens": 100, "cache_read_input_tokens": 900, "output_tokens": 50}}},
                {"timestamp": "2026-01-01T12:00:00Z", "type": "user", "message": {"content": "tool result"}},
                {"timestamp": "2026-01-01T12:01:00Z", "type": "assistant", "message": {"id": "m2", "usage": {"input_tokens": 2000, "output_tokens": 10}}},
            ]
            (directory / "agent-1.jsonl").write_text("\n".join(json.dumps(line) for line in lines), encoding="utf-8")
            report = stats.transcript_stats(Path(tmp))
        row = report["agents"][0]
        self.assertEqual((row["agent"], row["runs"], row["active_min"], row["avg_peak_context"], row["avg_output_tokens"]), ("architect", 1, 3.0, 2000, 60))
        self.assertEqual(report["idle_hours"], 2.0)


class CliTest(unittest.TestCase):
    """End-to-end through masflow.main() in a throwaway workspace."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_repo(Path(self.tmp.name), with_origin=False)
        self.run_cli("init", "--yes")

    def run_cli(self, *args: str) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        argv = sys.argv
        sys.argv = ["masflow.py", "--workspace", str(self.root), *args]
        code = 0
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                masflow.main()
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
        finally:
            sys.argv = argv
        return code, out.getvalue() + err.getvalue()

    def handoff(self) -> str:
        return (self.root / ".masflow" / "handoff.md").read_text(encoding="utf-8")

    def test_init_creates_a_workspace_that_passes_check(self):
        code, output = self.run_cli("check")
        self.assertEqual(code, 0, output)
        self.assertIn("masflow check: OK", output)

    def test_story_runs_end_to_end_without_an_agent(self):
        code, output = self.run_cli("log", "--agent", "planner", "--status", "success", "--message", "story written",
                                    "--set", "story=HU-1", "--set", "title=Demo: a title", "--set", "track=standard",
                                    "--set", "phase=4", "--set", "status=in_progress", "--set", "current_slice=1")
        self.assertEqual(code, 0, output)
        handoff = self.root / ".masflow" / "handoff.md"
        handoff.write_text(with_plan(self.handoff()), encoding="utf-8")
        slices = self.root / ".masflow" / "slices"
        slices.mkdir()
        (slices / "slice-1.md").write_text("# Slice 1\n", encoding="utf-8")

        self.assertEqual(self.run_cli("git", "create-branch", "--project", "app")[0], 0)
        (self.root / "feature.txt").write_text("x\n", encoding="utf-8")
        code, output = self.run_cli("git", "commit-slice", "--project", "app", "--slice", "1", "--message", "feature", "--files", "feature.txt")
        self.assertEqual(code, 0, output)
        code, output = self.run_cli("checks", "--project", "app", "--slice", "1", "--files", "feature.txt")
        self.assertTrue(json.loads(output)["data"]["not_configured"])
        self.run_cli("log", "--agent", "orchestrator", "--status", "success", "--message", "closed", "--slice", "1", "--slice-status", "closed")

        meta, body = masflow.split_front_matter(self.handoff())
        rows = {row["#"]: row for row in state.slice_rows(body)}
        self.assertEqual((rows["1"]["Status"], rows["1"]["Branch"]), ("closed", "masflow/HU-1"))
        self.assertEqual((meta["story"], meta["title"], meta["updated_by"]), ("HU-1", "Demo: a title", "orchestrator"))
        self.assertIn("masflow:commit_slice success", body)

        code, output = self.run_cli("git", "merge-story", "--project", "app")
        self.assertEqual((code, json.loads(output)["status"]), (3, "needs_human"))
        code, output = self.run_cli("git", "merge-story", "--project", "app", "--validated")
        self.assertEqual(code, 0, output)
        self.assertEqual(gitops.current_branch(self.root), "main")

        code, output = self.run_cli("archive-story")
        self.assertEqual(code, 0, output)
        self.assertEqual(masflow.split_front_matter(self.handoff())[0]["status"], "idle")
        self.assertTrue((self.root / ".masflow" / "archive" / "HU-1" / "slices" / "slice-1.md").exists())
        self.assertEqual(self.run_cli("archive-story")[0], 1)

        code, output = self.run_cli("stats", "--json", "--transcripts", str(self.root / "none"))
        report = json.loads(output)
        self.assertEqual(report["stories"][0]["story"], "HU-1")
        self.assertEqual(report["stories"][0]["slices_closed"], 1)
        self.assertIsNone(report["transcripts"])

    def test_check_fails_when_a_budget_is_exceeded(self):
        handoff = self.root / ".masflow" / "handoff.md"
        handoff.write_text(self.handoff().replace("## 1. User Story", "## 1. User Story\n" + "word " * 3000), encoding="utf-8")
        code, output = self.run_cli("check")
        self.assertEqual(code, 1)
        self.assertIn("budget: handoff §1 User Story", output)

    def test_log_rejects_unknown_keys_and_statuses(self):
        self.assertEqual(self.run_cli("log", "--agent", "x", "--status", "success", "--message", "m", "--set", "colour=red")[0], 1)
        self.assertEqual(self.run_cli("log", "--agent", "x", "--status", "done", "--message", "m")[0], 2)

    def test_verify_writes_the_log_and_accepts_a_baseline(self):
        config_file = self.root / "masflow.config.json"
        config = json.loads(config_file.read_text(encoding="utf-8"))
        config["projects"][0]["tests"]["full"] = "echo '1) FooTest::test_red'; exit 1"
        config_file.write_text(json.dumps(config), encoding="utf-8")

        code, output = self.run_cli("verify")
        result = json.loads(output)
        self.assertEqual((code, result["status"]), (2, "rejected"))
        self.assertEqual(result["data"]["projects"][0]["regressions"], ["FooTest::test_red"])

        code, output = self.run_cli("verify", "--accept-baseline")
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads((self.root / ".masflow" / "baseline.json").read_text(encoding="utf-8")), {"app": ["FooTest::test_red"]})
        code, output = self.run_cli("verify")
        self.assertEqual((code, json.loads(output)["status"]), (0, "success"))
        log = (self.root / ".masflow" / "verify_log.md").read_text(encoding="utf-8").splitlines()
        self.assertEqual(log[0], "# Verify log")
        self.assertIn(" red — ", log[1])
        self.assertIn(" green — ", log[-1])
        self.assertIn("regressions: 0", log[-1])


class RegressionTest(unittest.TestCase):
    """Bugs found reviewing the pipeline commands."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_commit_slice_leaves_what_the_human_had_staged_out_of_the_commit(self):
        repo = make_repo(self.root, with_origin=False)
        (repo / "old.txt").write_text("old\n", encoding="utf-8")
        sh(repo, "git", "add", "old.txt")
        sh(repo, "git", "commit", "-q", "-m", "old")
        gitops.create_branch(repo, "masflow/HU-1", "main")
        (repo / "human.txt").write_text("staged by the human\n", encoding="utf-8")
        sh(repo, "git", "add", "human.txt")
        (repo / "a.txt").write_text("a\n", encoding="utf-8")
        (repo / "old.txt").unlink()
        result = gitops.commit_slice(repo, "masflow/HU-1", "HU-1", "1", "slice", ["a.txt", "old.txt"])
        self.assertIn(result["status"], ("success", "warnings"), result)
        self.assertEqual(sorted(sh(repo, "git", "show", "--name-only", "--format=", "HEAD").split()), ["a.txt", "old.txt"])
        self.assertIn("human.txt", sh(repo, "git", "diff", "--cached", "--name-only"))

    def test_commit_slice_with_only_foreign_staged_changes_commits_nothing(self):
        repo = make_repo(self.root, with_origin=False)
        gitops.create_branch(repo, "masflow/HU-1", "main")
        (repo / "human.txt").write_text("x\n", encoding="utf-8")
        sh(repo, "git", "add", "human.txt")
        result = gitops.commit_slice(repo, "masflow/HU-1", "HU-1", "1", "slice", ["README.md"])
        self.assertEqual(result["status"], "error")

    def test_create_branch_starts_from_the_newest_main(self):
        repo = make_repo(self.root)
        other = self.root / "other"
        sh(self.root, "git", "clone", "-q", str(self.root / "origin.git"), "other")
        sh(other, "git", "config", "user.email", "o@example.com")
        sh(other, "git", "config", "user.name", "Other")
        (other / "new.txt").write_text("n\n", encoding="utf-8")
        sh(other, "git", "add", "new.txt")
        sh(other, "git", "commit", "-q", "-m", "someone else")
        sh(other, "git", "push", "-q", "origin", "main")
        self.assertEqual(gitops.create_branch(repo, "masflow/HU-2", "main")["status"], "success")
        self.assertTrue((repo / "new.txt").exists())

    def test_failed_merge_returns_to_the_story_branch(self):
        repo = make_repo(self.root, with_origin=False)
        gitops.create_branch(repo, "masflow/HU-1", "main")
        (repo / "a.txt").write_text("a\n", encoding="utf-8")
        gitops.commit_slice(repo, "masflow/HU-1", "HU-1", "1", "a", ["a.txt"])
        sh(repo, "git", "checkout", "-q", "main")
        (repo / "b.txt").write_text("b\n", encoding="utf-8")
        sh(repo, "git", "add", "b.txt")
        sh(repo, "git", "commit", "-q", "-m", "main moved")
        sh(repo, "git", "checkout", "-q", "masflow/HU-1")
        result = gitops.merge_story(repo, "masflow/HU-1", "main", "HU-1", "T", validated=True, use_gh=False)
        self.assertEqual(result["status"], "needs_human")
        self.assertEqual(gitops.current_branch(repo), "masflow/HU-1")

    def test_merge_story_through_a_pull_request(self):
        """The `gh` path, with a stand-in `gh` that merges the branch on the remote like GitHub would."""
        repo = make_repo(self.root)
        branch = "masflow/HU-9"
        gitops.create_branch(repo, branch, "main")
        (repo / "a.txt").write_text("a\n", encoding="utf-8")
        gitops.commit_slice(repo, branch, "HU-9", "1", "a", ["a.txt"])
        self.assertEqual(gitops.push_branch(repo, branch)["status"], "success")
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        calls = self.root / "gh_calls"
        stub = bin_dir / "gh"
        stub.write_text(f"""#!/bin/sh
echo "$@" >> {calls}
case "$1 $2" in
  "auth status") exit 0 ;;
  "pr create") echo "https://example.test/pr/1" ;;
  "pr merge")
    work=$(mktemp -d) && git clone -q {self.root / "origin.git"} "$work/c" && cd "$work/c" \
      && git -c user.email=gh@example.com -c user.name=gh merge -q --no-ff "origin/$3" -m "Merge pull request" \
      && git push -q origin main && git push -q origin --delete "$3" ;;
  *) exit 1 ;;
esac
""", encoding="utf-8")
        stub.chmod(0o755)
        import os
        old_path = os.environ["PATH"]
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{old_path}"
        self.addCleanup(os.environ.__setitem__, "PATH", old_path)
        result = gitops.merge_story(repo, branch, "main", "HU-9", "Title", body="summary", validated=True)
        self.assertEqual(result["status"], "success", result)
        self.assertEqual(result["data"]["pr_url"], "https://example.test/pr/1")
        self.assertEqual(gitops.current_branch(repo), "main")
        self.assertTrue((repo / "a.txt").exists())
        self.assertFalse(gitops.branch_exists(repo, branch))
        log = calls.read_text(encoding="utf-8")
        self.assertIn("pr create --base main --head masflow/HU-9 --title HU-9: Title --body summary", log)
        self.assertIn("pr merge masflow/HU-9 --merge --delete-branch", log)

    def test_merge_story_stops_when_the_pull_request_cannot_be_merged(self):
        repo = make_repo(self.root)
        branch = "masflow/HU-9"
        gitops.create_branch(repo, branch, "main")
        (repo / "a.txt").write_text("a\n", encoding="utf-8")
        gitops.commit_slice(repo, branch, "HU-9", "1", "a", ["a.txt"])
        gitops.push_branch(repo, branch)
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        stub = bin_dir / "gh"
        stub.write_text('#!/bin/sh\ncase "$1 $2" in "auth status") exit 0;; "pr create") echo url;; *) echo "branch protection" >&2; exit 1;; esac\n', encoding="utf-8")
        stub.chmod(0o755)
        import os
        old_path = os.environ["PATH"]
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{old_path}"
        self.addCleanup(os.environ.__setitem__, "PATH", old_path)
        result = gitops.merge_story(repo, branch, "main", "HU-9", "Title", validated=True)
        self.assertEqual(result["status"], "needs_human")
        self.assertIn("branch protection", result["data"]["git_output"])
        self.assertEqual(gitops.current_branch(repo), branch)
        self.assertFalse((repo / "a.txt").exists() and gitops.current_branch(repo) == "main")

    def test_shell_timeout_kills_the_whole_process_tree(self):
        marker = self.root / "survived"
        code, output = runs.shell(f"(sleep 2; touch {marker}) & sleep 30", 1)
        self.assertEqual(code, runs.TIMEOUT_CODE)
        self.assertIn("timed out", output)
        import time
        time.sleep(2.5)
        self.assertFalse(marker.exists(), "a child of the timed-out command kept running")

    def test_verify_timeout_is_an_error_even_when_failures_match_the_baseline(self):
        project = {"name": "app", "tests": {"full": "run"}}
        fake = lambda command, timeout: (runs.TIMEOUT_CODE, "FAILED tests/test_a.py::test_x - boom\n[masflow] timed out after 1s")
        result = runs.verify_project(project, lambda s: s, ["tests/test_a.py::test_x"], self.root / "log", run=fake)
        self.assertEqual(result["result"], "error")

    def test_verify_ignores_a_junit_report_left_by_an_earlier_run(self):
        report = self.root / "junit.xml"
        report.write_text('<testsuite><testcase classname="A" name="old"><failure/></testcase></testsuite>', encoding="utf-8")
        project = {"name": "app", "tests": {"full": "run", "junit": str(report)}}
        result = runs.verify_project(project, lambda s: s, [], self.root / "log", run=lambda c, t: (0, "ok"))
        self.assertEqual((result["result"], result["failed"]), ("green", []))

    def test_fix_slices_do_not_count_against_the_story_size(self):
        rows = "".join(f"| {i} | s | app | closed |\n" for i in range(1, 7)) + "| fix-1 | findings | app | pending |\n"
        handoff = "---\nstory: HU-1\n---\n## 3. Technical Plan\n| # | Title | Project | Status |\n|---|---|---|---|\n" + rows + "## 4. Execution Log\n"
        state_dir = self.root / ".masflow"
        state_dir.mkdir()
        (state_dir / "handoff.md").write_text(handoff, encoding="utf-8")
        self.assertEqual([p for p in state.budget_problems(state_dir, {}) if "slices in the story" in p], [])
        text, found = state.set_slice_row(handoff, "fix-1", {"Status": "closed"})
        self.assertTrue(found)

    def test_parallel_log_calls_do_not_lose_lines(self):
        ws_root = make_repo(self.root, with_origin=False)
        cli = [sys.executable, str(Path(masflow.__file__)), "--workspace", str(ws_root)]
        subprocess.run([*cli, "init", "--yes"], capture_output=True, check=True)
        subprocess.run([*cli, "log", "--agent", "planner", "--status", "success", "--message", "start", "--set", "story=HU-1"],
                       capture_output=True, check=True)
        procs = [subprocess.Popen([*cli, "log", "--agent", "guard", "--status", "success", "--message", f"parallel {i}"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for i in range(12)]
        self.assertEqual([p.wait() for p in procs], [0] * 12)
        handoff = (ws_root / ".masflow" / "handoff.md").read_text(encoding="utf-8")
        self.assertEqual(sum("parallel " in line for line in handoff.splitlines()), 12)
        self.assertEqual(len(state.read_events(ws_root / ".masflow")), 13)

    def test_checks_skip_files_the_slice_deleted(self):
        ws_root = make_repo(self.root, with_origin=False)
        cli = [sys.executable, str(Path(masflow.__file__)), "--workspace", str(ws_root)]
        subprocess.run([*cli, "init", "--yes"], capture_output=True, check=True)
        config_file = ws_root / "masflow.config.json"
        config = json.loads(config_file.read_text(encoding="utf-8"))
        config["projects"][0]["slice_checks"] = ["cd {project} && ls {files}"]
        config_file.write_text(json.dumps(config), encoding="utf-8")
        proc = subprocess.run([*cli, "checks", "--project", "app", "--files", "README.md", "deleted.txt"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["data"]["files"], ["README.md"])

    def test_executor_self_check_does_not_write_the_handoff(self):
        ws_root = make_repo(self.root, with_origin=False)
        cli = [sys.executable, str(Path(masflow.__file__)), "--workspace", str(ws_root)]
        subprocess.run([*cli, "init", "--yes"], capture_output=True, check=True)
        subprocess.run([*cli, "log", "--agent", "planner", "--status", "success", "--message", "start", "--set", "story=HU-1"],
                       capture_output=True, check=True)
        before = (ws_root / ".masflow" / "handoff.md").read_text(encoding="utf-8")
        subprocess.run([*cli, "checks", "--no-log", "--project", "app", "--files", "README.md"], capture_output=True)
        self.assertEqual((ws_root / ".masflow" / "handoff.md").read_text(encoding="utf-8"), before)
        self.assertEqual(len(state.read_events(ws_root / ".masflow")), 1)
        for name in ("executor.md", "fixer.md"):
            self.assertIn("checks --no-log", (masflow.CORE_DIR / name).read_text(encoding="utf-8"), name)


if __name__ == "__main__":
    unittest.main()
