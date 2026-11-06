# Running MAS-Flow with Claude Code

`masflow.py` turns the portable agent prompts into Claude Code **subagents**, an orchestrator **skill**, **hooks** and **permissions**.

## 1. Mapping

| MAS-Flow concept | Claude Code primitive |
|---|---|
| Orchestrator | The **main session**, driven by the `/masflow` skill (`.claude/skills/masflow/SKILL.md`). Subagents cannot spawn subagents, so the orchestrator cannot be one. |
| Every other role | **Subagent** in `.claude/agents/<name>.md`, invoked with the `Agent` tool. |
| Role boundaries | The subagent's `tools:`. Executors have no Bash (cannot run tests); researcher, tester and guard have no Edit/Write (cannot change code). A missing tool cannot be ignored by the model. |
| Model per role | The subagent's `model:` (`fable`, `opus`, `sonnet`, `haiku`, `inherit` or a full model ID), overridable in `masflow.config.json → models`. Per-mode overrides (`mode_models`, e.g. `{"guard": {"plan_review": "fable"}}`) are passed by the orchestrator as the Agent call's `model`. |
| Environment rules | `PreToolUse` hook `command_guard.py`, configured by `command_guard` in the config. |
| Pipeline state at session start | `SessionStart` hook `handoff_status.py`. |
| Workspace instructions | `.claude/MASFLOW.md` (generated), imported from `CLAUDE.md` with `@.claude/MASFLOW.md`. |
| Human gates | `AskUserQuestion` from the orchestrator. |
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
| fixer | top | Rare (only after the retry budget is exhausted) and needs root-cause diagnosis. |
| executors, guard `code_audit`, documenter | `sonnet` | Run every slice; writing and auditing code. |
| researcher, tester, terminal_executor | `haiku` | Mechanical steps: locating files, running commands, git. `researcher` `survey` on a large scope → `sonnet` via `mode_models`. |

Measure before moving a role up: on one workspace (~1 450 agent runs) the executors took ~54 % of agent wall time and the architect ~36 min per run, while time inside the test commands was under 3 % — the cost is the agent work around a step, not the step. Each subagent has its own context window; the orchestrator only receives its final message. Choose the main session's model with `/model` — routing rarely needs the top model.

### Tests and time

Full suites are not the slow part (minutes); an agent reading, re-running and comparing their output is. Hence the four test tiers in the shared protocol: slice self-check, an audit without tests, related tests at story close, and full suites only in the daily `/masflow verify` (and before a deploy). Make the full suite itself fast too: run it in parallel when the stack supports it (e.g. Laravel `test --parallel` with paratest), and keep the known baseline failures listed in `lessons.md` so the comparison is by test name.

## 4. Daily usage

| Goal | How |
|---|---|
| Map an existing codebase | `/masflow map` (or `/masflow map <project or area>`) |
| See / pick work | `/masflow board` |
| New feature | `/masflow <goal or card ID>` → planner options → you choose → pipeline continues |
| Continue | `/masflow next` |
| State | `/masflow status` (or `python3 MAS-Flow/scripts/masflow.py status`) |
| Full suites (end of day / before deploy) | `/masflow verify` |
| One agent ad hoc | *"Use the researcher agent to find …"* |
| List agents | `/agents` |

## 5. Hooks

- **`command_guard.py`** (PreToolUse/Bash): splits the command respecting quotes and command substitutions, and blocks programs listed in `command_guard.blocked` with the configured `hint` (exit 2 → the model sees the hint and retries correctly).
- **`handoff_status.py`** (SessionStart): prints story, track, phase, status, slice and next agent.

Both locate `masflow.config.json` from `$CLAUDE_PROJECT_DIR`, so they work unchanged in any workspace.
