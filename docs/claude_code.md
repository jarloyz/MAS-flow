# Running MAS-Flow with Claude Code

`masflow.py` turns the portable agent prompts into Claude Code **subagents**, an orchestrator **skill**, **hooks** and **permissions**.

## 1. Mapping

| MAS-Flow concept | Claude Code primitive |
|---|---|
| Orchestrator | The **main session**, driven by the `/masflow` skill (`.claude/skills/masflow/SKILL.md`). Subagents cannot spawn subagents, so the orchestrator cannot be one. |
| Every other role | **Subagent** in `.claude/agents/<name>.md`, invoked with the `Agent` tool. |
| Role boundaries | The subagent's `tools:`. Executors have no Bash (cannot run tests); researcher, tester and guard have no Edit/Write (cannot change code). A missing tool cannot be ignored by the model. |
| Model per role | The subagent's `model:` (`opus`, `sonnet`, `haiku`, `inherit` or a full model ID), overridable in `masflow.config.json → models`. |
| Environment rules | `PreToolUse` hook `command_guard.py`, configured by `command_guard` in the config. |
| Pipeline state at session start | `SessionStart` hook `handoff_status.py`. |
| Workspace instructions | `.claude/MASFLOW.md` (generated), imported from `CLAUDE.md` with `@.claude/MASFLOW.md`. |
| Human gates | `AskUserQuestion` from the orchestrator. |

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

On a Claude subscription there is no per-token bill, but usage limits drain faster with bigger models. Reserve `opus` for decisions (planner, architect), `sonnet` for writing and auditing code, `haiku` for mechanical steps (git, running tests, locating files). Each subagent has its own context window; the orchestrator only receives its final message. Choose the main session's model with `/model` — routing rarely needs the top model.

## 4. Daily usage

| Goal | How |
|---|---|
| Map an existing codebase | `/masflow map` (or `/masflow map <project or area>`) |
| See / pick work | `/masflow board` |
| New feature | `/masflow <goal or card ID>` → planner options → you choose → pipeline continues |
| Continue | `/masflow next` |
| State | `/masflow status` (or `python3 MAS-Flow/scripts/masflow.py status`) |
| One agent ad hoc | *"Use the researcher agent to find …"* |
| List agents | `/agents` |

## 5. Hooks

- **`command_guard.py`** (PreToolUse/Bash): splits the command respecting quotes and command substitutions, and blocks programs listed in `command_guard.blocked` with the configured `hint` (exit 2 → the model sees the hint and retries correctly).
- **`handoff_status.py`** (SessionStart): prints story, track, phase, status, slice and next agent.

Both locate `masflow.config.json` from `$CLAUDE_PROJECT_DIR`, so they work unchanged in any workspace.
