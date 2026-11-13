# Running MAS-Flow with Claude Code

`masflow.py` turns the portable agent prompts into Claude Code **subagents**, an orchestrator **skill**, **hooks** and **permissions**, and provides the pipeline steps that need no model as commands.

## 1. Mapping

| MAS-Flow concept | Claude Code primitive |
|---|---|
| Orchestrator | The **main session**, driven by the `/masflow` skill (`.claude/skills/masflow/SKILL.md`). Subagents cannot spawn subagents, so the orchestrator cannot be one. |
| Every other role | **Subagent** in `.claude/agents/<name>.md`, invoked with the `Agent` tool. |
| Mechanical steps | `masflow.py git · checks · verify · log · archive-story`, run by the main session with Bash. No subagent, no model. |
| Role boundaries | The subagent's `tools:`. Researcher, tester, guard and security have no Edit/Write (cannot change code); planner, architect and documenter have no Bash. A missing tool cannot be ignored by the model. Executors and the fixer do have Bash, for their self-check only: their prompt restricts it to the test and check commands, and the permission rules below should not allow them more. |
| Model per role | The subagent's `model:` (`fable`, `opus`, `sonnet`, `haiku`, `inherit` or a full model ID), overridable in `masflow.config.json → models`. Per-mode overrides (`mode_models`, e.g. `{"guard": {"plan_review": "fable"}}`) are passed by the orchestrator as the Agent call's `model`. |
| Environment rules | `PreToolUse` hook `command_guard.py`, configured by `command_guard` in the config. |
| Pipeline state at session start | `SessionStart` hook `handoff_status.py`. |
| Workspace instructions | `.claude/MASFLOW.md` (generated), imported from `CLAUDE.md` with `@.claude/MASFLOW.md`. |
| Human gates | `AskUserQuestion` from the orchestrator (option, track, epic split, retries exhausted, `needs_human`). The merge is not a gate: it runs when every story-close gate is green. |
| Standalone tools (`kind: standalone`) | **Skill** in `.claude/skills/<name>/SKILL.md` (OpenCode: primary agent). Used directly by the Human outside the pipeline: no handoff protocol, not in the orchestrator roster. |

## 2. Generation

```bash
python3 MAS-Flow/scripts/masflow.py sync
```

For each agent, the generator:

1. Resolves layers: `agents/core/` → enabled `agents/packs/<pack>/` → project `<state_dir>/agents/`. `extends:` chains are appended as `## SPECIALIZATION` sections.
2. Replaces placeholders (`{{HANDOFF}}`, `{{PROJECTS}}`, `{{TEST_COMMANDS}}`, ...) from `masflow.config.json`; unknown placeholders are an error.
3. Appends the shared protocol (`_shared.md`) and the Claude Code runtime notes (no working-directory parameter in Bash → `cd <abs> && cmd`; Edit parameters; final message = result envelope).
4. Maps abstract tools: `read → Read`, `search → Grep, Glob`, `edit → Edit`, `write → Write`, `shell → Bash`.
5. Merges `.claude/settings.json`: replaces only MAS-Flow-owned hooks and adds the configured permissions; everything else is preserved.
6. Removes generated agents that no longer exist (hand-written agents are never touched).

## 3. Models and quota

On a Claude subscription there is no per-token bill, but usage limits drain faster with bigger models. Spend the top model where one decision steers a lot of later work, not where an agent runs many times:

| Role / mode | Model | Why |
|---|---|---|
| planner, architect | top (`fable`; `opus` where Fable is not available) | One run per story; a wrong option or plan costs every slice after it. |
| guard `plan_review` (via `mode_models`) | top | One run per story; design and security flaws are cheapest to catch before code exists. |
| guard `story_audit` (via `mode_models`, optional) | top or `sonnet` | One run per story over the whole diff, including the AC proof. Move it up if `stats` shows escapes it should have caught. |
| fixer | top | Rare (only after the retry budget is exhausted) and needs root-cause diagnosis. |
| security (`threat_model`, `story_audit`) | top | Once or twice per story; adversarial review of the whole diff. Re-audits read only the fix diff. |
| executors, guard `code_audit`, documenter | `sonnet` | Executors run every slice; the slice audit only on high-risk slices. |
| researcher, tester | `haiku` | Locating files, running commands. `researcher` `survey` on a large scope → `sonnet` via `mode_models`. |
| git, slice checks, verify, logging | none | `masflow.py` commands. |

Measure before moving a role up or a gate down: `/masflow stats` (or `masflow.py stats`) reads the event log and the Claude Code transcripts of the workspace and reports time, runs, peak context and output size per agent, and runs versus rejections per gate. The cost is the agent work around a step, not the step: on the workspaces this was tuned on, time inside test commands was a few percent, while planning, design and audit took about two thirds of the agent time and writing code under a fifth. That is why the plan is contract-level, the handoff and the rules have size budgets, and the per-slice audit is risk-based.

Each subagent has its own context window; the orchestrator only receives its final message. Choose the main session's model with `/model` — routing rarely needs the top model — and **start each story in a fresh session** (`/clear`): the state is in `.masflow/`, and a session that has run several stories pays for all of them on every turn.

### Tests and time

Full suites are not the slow part (minutes); an agent reading, re-running and comparing their output is. Hence the tiers in the shared protocol: slice self-check, deterministic slice checks, related tests at story close, and full suites only in the daily `/masflow verify` (and before a deploy) — which is a script: it runs the suites, extracts the failing test names (from a JUnit report if `tests.junit` is set, from the output otherwise) and compares them with `.masflow/baseline.json`. Make the full suite itself fast too: run it in parallel when the stack supports it (e.g. Laravel `test --parallel` with paratest). Record the known failures once with `masflow.py verify --accept-baseline`.

### Project configuration for the deterministic steps

```json
{
  "budgets": {"story_slices": 6, "handoff_kb": 40, "plan_kb": 12, "slice_spec_kb": 6, "active_rules": 30},
  "gates": {"guard_code_audit": "risk"},
  "parallel": {"slices": 1},
  "projects": [{
    "name": "app",
    "slice_checks": [
      "cd {project} && ./vendor/bin/pint --test {files}",
      {"run": "cd {project} && ./vendor/bin/phpstan analyse --no-progress {files}", "ext": [".php"], "under": ["app/", "routes/"]}
    ],
    "acceptance": ["cd {project} && ./scripts/smoke.sh"],
    "tests": {"full": "…", "verify": "cd {project} && php artisan test --parallel --log-junit storage/junit.xml", "junit": "{project}/storage/junit.xml"}
  }]
}
```

- `slice_checks` — commands with a `{files}` placeholder (paths relative to the project), run by `masflow.py checks` on every slice. `ext`/`under` restrict which files a check receives. Without them the executor's self-check is the only slice check. A check must be green on the code as it is today: `checks` rejects on any non-zero exit, so keep pre-existing errors in the tool's own baseline (e.g. a PHPStan baseline) or every slice touching an old file is rejected. Files the slice deleted are skipped. Executors run the same command with `--no-log` in their self-check; only the orchestrator's run is recorded as the gate.
- `acceptance` — commands that exercise the running application; the tester runs them at story close.
- `gates.guard_code_audit` — `risk` (default: the guard audits only high-risk slices) or `always`.
- `parallel.slices` — how many executors may run at once on slices of the same wave. Keep `1` unless the test environments tolerate concurrent runs.
- `budgets` — see the [Protocol](protocol.md#3-context-budgets).

Recommended permissions for the orchestrator's commands (`{masflow}` expands to `python3 <path>/masflow.py`):

```json
"allow": ["Bash({masflow} status:*)", "Bash({masflow} check:*)", "Bash({masflow} stats:*)", "Bash({masflow} log:*)",
          "Bash({masflow} related-tests:*)", "Bash({masflow} checks:*)",
          "Bash({masflow} git create-branch:*)", "Bash({masflow} git commit-slice:*)", "Bash({masflow} git rollback-slice:*)",
          "Bash({masflow} git push-branch:*)", "Bash({masflow} git merge-story:*)",
          "Bash({masflow} verify:*)", "Bash({masflow} archive-story:*)"],
"deny":  ["Bash({masflow} verify --accept-baseline:*)"]
```

The config template ships with all of them: the merge is automatic, and a permission prompt on `push-branch` or `merge-story` would be a Human gate in disguise. Remove those two lines from your workspace config if you want to approve every push and merge by hand. `sync` only adds the rules listed in **your** `masflow.config.json`; a workspace created before this list must add them there.

## 4. Daily usage

| Goal | How |
|---|---|
| Map an existing codebase | `/masflow map` (or `/masflow map <project or area>`) |
| See / pick work | `/masflow board` |
| New feature | `/masflow <goal or card ID>` → planner options → you choose → pipeline continues |
| Continue | `/masflow next` |
| State | `/masflow status` (or `python3 MAS-Flow/scripts/masflow.py status`) |
| Full suites (end of day / before deploy) | `/masflow verify` |
| Where the time goes, what each gate catches | `/masflow stats` |
| Validate config, prompts and context budgets | `python3 MAS-Flow/scripts/masflow.py check` |
| One agent ad hoc | *"Use the researcher agent to find …"* |
| List agents | `/agents` |

## 5. Hooks

- **`command_guard.py`** (PreToolUse/Bash): splits the command respecting quotes and command substitutions, and blocks programs listed in `command_guard.blocked` with the configured `hint` (exit 2 → the model sees the hint and retries correctly).
- **`handoff_status.py`** (SessionStart): prints story, track, phase, status, slice and next agent — which is all a fresh session needs to continue a story.
- **`format_on_edit.py`** (PostToolUse, only when a project sets `format_on_edit`): formats each edited file so formatting never reaches a gate.

All locate `masflow.config.json` from `$CLAUDE_PROJECT_DIR`, so they work unchanged in any workspace.
