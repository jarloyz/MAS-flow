"""Lint for the methodology itself: prompts render, stay consistent with the protocol, and docs do not drift."""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import masflow  # noqa: E402
import state  # noqa: E402

ROOT = masflow.MASFLOW_DIR
CORE = sorted(p for p in masflow.CORE_DIR.glob("*.md"))
DOCS = [ROOT / "README.md", ROOT / "MANIFESTO.md", *sorted((ROOT / "docs").glob("*.md"))]

# Stack-specific words that belong in agents/packs/, never in the portable core.
STACK_WORDS = re.compile(r"\b(sail|phpstan|larastan|pint|artisan|composer|phpunit|pest|laravel|eloquent|filament|livewire|npm|jest)\b(?!\.\w)", re.I)

# Things the pipeline no longer does. A doc or prompt that mentions them is describing an older flow.
STALE = {
    r"merge_slice": "slices are not merged one by one: the story branch is merged once (merge-story)",
    r"slice branch": "there is one branch per story, not per slice",
    r"masflow/<HU>-slice": "there is one branch per story, not per slice",
    r"Executors have no Bash": "executors run a restricted self-check",
    r"never runs them or any shell command": "executors run a restricted self-check",
    r"handoff_reset|Reset `\{\{HANDOFF\}\}`": "the handoff is archived by `masflow.py archive-story`, not reset by the documenter",
    r"every (slice )?merge": "the merge is automatic once the story-close gates are green; it is not a Human gate",
    r"Merge approval|merge approval": "the merge is automatic once the story-close gates are green; it is not a Human gate",
    r"calls each agent separately|Calls Agents Manually": "the orchestrator may be an AI session; manual operation is one option",
    r"after tester passed": "the tester runs at story close, not before the slice audit",
    r"GPT-4o|Claude 3\.5": "name model tiers, not dated model versions",
}


def workspace(packs: list[str], runtimes: list[str]) -> masflow.Workspace:
    config = json.loads((masflow.TEMPLATES_DIR / masflow.CONFIG_NAME).read_text(encoding="utf-8"))
    config.update({"packs": packs, "runtimes": runtimes})
    return masflow.Workspace(Path("/workspace"), config)


class RenderTest(unittest.TestCase):
    def test_every_agent_renders_for_every_runtime_with_all_packs(self):
        packs = sorted(p.name for p in masflow.PACKS_DIR.iterdir() if p.is_dir())
        ws = workspace(packs, ["claude-code", "opencode"])
        agents = masflow.resolve_agents(ws)
        values = masflow.placeholder_values(ws, agents)
        self.assertTrue(any(a.is_orchestrator for a in agents.values()))
        for agent in agents.values():
            for adapter in (masflow.CLAUDE_ORCHESTRATOR_ADAPTER if agent.is_orchestrator else masflow.CLAUDE_AGENT_ADAPTER.format(shell=""),
                            masflow.OPENCODE_ORCHESTRATOR_ADAPTER if agent.is_orchestrator else masflow.OPENCODE_AGENT_ADAPTER):
                text = masflow.full_prompt(agent, values, adapter)
                self.assertEqual(masflow.PLACEHOLDER.findall(text), [], f"{agent.name}: unresolved placeholders")
                self.assertTrue("Result envelope" in text, f"{agent.name}: shared protocol missing")

    def test_sync_writes_agents_and_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = json.loads((masflow.TEMPLATES_DIR / masflow.CONFIG_NAME).read_text(encoding="utf-8"))
            config["runtimes"] = ["claude-code", "opencode"]
            ws = masflow.Workspace(Path(tmp), config)
            agents = masflow.resolve_agents(ws)
            values = masflow.placeholder_values(ws, agents)
            for runtime in config["runtimes"]:
                masflow.RUNTIMES[runtime](ws, agents, values)
            skill = (Path(tmp) / ".claude" / "skills" / "masflow" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("masflow.py log", skill)
            self.assertTrue((Path(tmp) / ".claude" / "agents" / "guard.md").exists())
            opencode = (Path(tmp) / ".opencode" / "agents" / "orchestrator.md").read_text(encoding="utf-8")
            self.assertIn("  bash: true", opencode)


class ProtocolConsistencyTest(unittest.TestCase):
    def test_agents_only_use_canonical_statuses(self):
        for path in CORE:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.startswith("Status:"):
                    continue
                used = re.findall(r"`(\w+)`(?= ?\(|,|\.| \()", line) or re.findall(r"`(\w+)`", line)
                unknown = [s for s in used if s not in state.STATUSES and s not in ("warning", "info", "critical", "verify")]
                self.assertEqual(unknown, [], f"{path.name}: {line}")

    def test_core_agents_declare_what_the_generator_needs(self):
        for path in CORE:
            if path.name.startswith("_"):
                continue
            meta, body = masflow.split_front_matter(path.read_text(encoding="utf-8"))
            self.assertTrue(meta.get("name") and meta.get("description"), path.name)
            if meta.get("kind") != "orchestrator":
                self.assertTrue(meta.get("tools"), path.name)
                self.assertTrue(re.search(r"Status:|`status: ", body), f"{path.name} does not say which statuses it returns")

    def test_only_agents_that_write_files_can_edit(self):
        read_only = {"researcher", "tester", "guard", "security", "terminal_executor"}
        for path in CORE:
            meta, _ = masflow.split_front_matter(path.read_text(encoding="utf-8"))
            if meta.get("name") in read_only:
                self.assertFalse({"edit", "write"} & set(meta.get("tools") or []), path.name)

    def test_core_is_stack_neutral(self):
        for path in CORE:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                # examples in parentheses or after "e.g." may name a stack; instructions may not
                instruction = re.sub(r"\(e\.g\.[^)]*\)|e\.g\. [^.;]*", "", line)
                match = STACK_WORDS.search(instruction)
                self.assertIsNone(match, f"{path.name}:{number} names '{match.group(0) if match else ''}': move it to a pack")

    def test_pipeline_commands_in_prompts_exist_in_the_cli(self):
        known = {"status", "check", "stats", "log", "git", "checks", "verify", "archive-story", "related-tests", "sync", "init"}
        git_operations = {"create-branch", "commit-slice", "rollback-slice", "push-branch", "merge-story"}
        for path in CORE:
            text = path.read_text(encoding="utf-8")
            for command in re.findall(r"\{\{MASFLOW_CLI\}\} ([a-z-]+)", text):
                self.assertIn(command, known, f"{path.name}: unknown command {command}")
            for operation in re.findall(r"\{\{MASFLOW_CLI\}\} git ([a-z-]+)", text):
                self.assertIn(operation, git_operations, f"{path.name}: unknown git operation {operation}")

    def test_budgets_in_the_config_template_match_the_defaults(self):
        config = json.loads((masflow.TEMPLATES_DIR / masflow.CONFIG_NAME).read_text(encoding="utf-8"))
        self.assertEqual(config["budgets"], state.DEFAULT_BUDGETS)

    def test_prompts_stay_small(self):
        # a prompt is read on every run of its agent: keep each core file under 18 KB
        for path in CORE:
            self.assertLess(path.stat().st_size, 18 * 1024, path.name)


class DriftTest(unittest.TestCase):
    def test_docs_and_prompts_do_not_describe_an_older_flow(self):
        files = DOCS + CORE + sorted(masflow.PACKS_DIR.glob("*/*.md")) + sorted(masflow.TEMPLATES_DIR.glob("*.md"))
        problems = []
        for path in files:
            text = path.read_text(encoding="utf-8")
            for pattern, reason in STALE.items():
                for match in re.finditer(pattern, text):
                    line = text.count("\n", 0, match.start()) + 1
                    problems.append(f"{path.relative_to(ROOT)}:{line} '{match.group(0)}' — {reason}")
        self.assertEqual(problems, [], "\n" + "\n".join(problems))

    def test_tracks_are_described_the_same_everywhere(self):
        # the fast track has no guard and no architect; the merge follows the story close
        for path in (ROOT / "docs" / "protocol.md", masflow.CORE_DIR / "orchestrator.md"):
            row = next(line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("| `fast` |"))
            self.assertIn("no guard", row, path.name)
            self.assertNotIn("Human", row.split("|")[3], path.name)

    def test_docs_mention_every_core_agent_and_command(self):
        roles = (ROOT / "docs" / "roles.md").read_text(encoding="utf-8").lower()
        for path in CORE:
            if not path.name.startswith("_"):
                self.assertIn(path.stem.replace("_", " "), roles, f"docs/roles.md does not describe {path.stem}")
        protocol = (ROOT / "docs" / "protocol.md").read_text(encoding="utf-8")
        for command in ("masflow.py log", "masflow.py verify", "masflow.py archive-story", "masflow.py stats", "masflow.py check"):
            self.assertIn(command, protocol)


if __name__ == "__main__":
    unittest.main()
