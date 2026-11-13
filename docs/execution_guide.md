# Execution Guide: Running MAS-Flow

MAS-Flow is a methodology with a reference implementation. There are two ways to run it, and both follow the same [Protocol](protocol.md):

1. **With a supported runtime** (Claude Code, OpenCode) — `masflow.py sync` generates the agents and an AI orchestrator drives the pipeline. See [Running MAS-Flow with Claude Code](claude_code.md).
2. **By hand, or with your own framework** — you (or your script) play the orchestrator: give each agent its prompt and its inputs, run the `masflow.py` commands yourself, and keep `handoff.md` true. This page covers that case.

## 1. Agents are the prompts in `agents/`

Do not write personas from memory: each role is defined by its file in [`agents/core/`](../agents/core/) (plus stack specializations in `agents/packs/`), with the shared protocol [`_shared.md`](../agents/core/_shared.md) appended. `masflow.py sync` renders them for a workspace — placeholders such as `{{HANDOFF}}` or `{{TEST_COMMANDS}}` replaced with your paths and commands — into `.claude/agents/` or `.opencode/agents/`. With another framework, use those rendered files as system prompts.

## 2. What each agent receives

Agents do **not** need the whole codebase, and they do not need the whole state directory either. Give each one only this:

| Agent | Reads |
| --- | --- |
| **Planner** | handoff, `core_architecture.md`, product/functional/repository maps, lessons, board |
| **Researcher** | handoff §1, repository and functional maps, the codebase (search) |
| **Architect** | handoff §1-§2, `core_architecture.md`, product and functional maps, lessons, the files named as pointers |
| **Executor / Fixer** | its slice spec (`slices/slice-<id>.md`), the pointers and files of that slice, `core_architecture.md`, Active Rules |
| **Guard** | `core_architecture.md`, Active Rules, handoff §1 and §3, and — by mode — the slice specs, one slice's files, or the story diff |
| **Security** | `core_architecture.md`, handoff §1 and §3, the slice specs (threat model) or the whole story diff (audit) |
| **Tester** | handoff §1 and the AC traceability table, the test commands |
| **Documenter** | handoff, history, maps, lessons, board |

Every agent ends its answer with the **result envelope** (`status`, `summary`, `data`, `handoff_log`); the status decides the next step.

## 3. Advancing the flow by hand

```bash
M="python3 MAS-Flow/scripts/masflow.py"
```

1. **Plan.** Run the *Planner* with your goal. Choose one of its options; run it again with your choice so it writes the User Story.
   `$M log --agent planner --status success --message "story written" --set story=HU-12 --set track=full --set phase=2 --set status=in_progress --set next_agent=researcher`
2. **Research.** Run the *Researcher*; copy its pointers into handoff §2.
3. **Design** (`full` track). Run the *Architect* (plan in §3, one spec per slice), then the *Guard* in `plan_review` and the *Security* auditor in `threat_model` — at the same time if you can. Rejected → back to the Architect with the findings.
4. **Each slice:**
   ```bash
   $M git create-branch --project app
   #   run the slice's Executor with its slice spec
   $M git commit-slice --project app --slice 1 --message "repository contract" --files app/Domain/X.php tests/XTest.php
   $M checks --project app --slice 1 --files app/Domain/X.php tests/XTest.php
   #   high-risk slice only: run the Guard in code_audit
   $M log --agent orchestrator --status success --message "slice 1 closed" --slice 1 --slice-status closed --set current_slice=2
   ```
   A `rejected` result goes back to the same Executor with the exact findings (two rounds, then decide: Fixer, `git rollback-slice`, or stop).
5. **Story close.** Run *Security* `story_audit`, *Guard* `story_audit` and the *Tester* (`scope: story`) — in parallel if you can. All green:
   ```bash
   $M git push-branch --project app
   $M git merge-story --project app --validated
   ```
6. **Consolidate.** Run the *Documenter* (Phase 6), then `$M archive-story`.
7. **End of day:** `$M verify`. **Any time:** `$M status`, `$M check`, `$M stats`.

`git`, `checks`, `verify` and `archive-story` write their own Execution Log line; `log` is for agent results and for moving the front matter. `checks --no-log` runs the same checks without recording them (it is what an executor uses in its self-check).

## 4. Parallelism

- **Inside a story:** the plan review and the threat model run together; so do the three story-close gates. Slices of the same wave (no shared file, no open dependency) can run together when the projects' test environments tolerate concurrent runs — set `parallel.slices` in the config.
- **Across stories:** the board has a WIP limit of one story per workspace, because one `handoff.md` describes one story. To work on two stories at once, use two working copies of the workspace (for example `git worktree`), each with its own state directory, and merge them one after the other: the second story must be re-validated on top of the new main (`merge-story` stops and tells you).

## 5. Keeping it fast

- Start each story in a fresh orchestrator session; the state is on disk.
- Keep the handoff, the slice specs and the Active Rules inside their budgets — `$M check` tells you when they are not.
- Look at `$M stats` before changing a gate or a model: it shows which agents take the time and which gates actually reject.
