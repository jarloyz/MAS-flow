## MAS-FLOW SHARED PROTOCOL (binding for every agent)

### State files — `{{STATE_DIR}}/`

| File | Purpose | Who writes it |
|---|---|---|
| `handoff.md` | State of the current story. Single source of truth for the pipeline. | Front matter + Execution Log: **orchestrator only**. §1 User Story: planner. §3 Technical Plan: architect. Reset: documenter (Phase 6). |
| `core_architecture.md` | Canonical architecture contract (stack, patterns, bounded contexts, rules). | documenter, only with Human approval |
| `product_map.md` | What the product does: areas → capabilities (`CAP-<AREA>-<NN>`) with status, entry points, components, stories. | documenter |
| `board.md` | Task flow of the workspace: Inbox → Ready → In Progress → Blocked → Done. WIP 1. | planner/documenter add to Inbox · orchestrator moves to In Progress/Blocked · documenter moves to Done |
| `repository_map.md` | Where things live, by project and area (never by story). | documenter |
| `functional_map.md` | What does X / where is X: one entry per canonical component. Prevents duplicate implementations. | documenter |
| `lessons.md` | Recurring failures turned into rules. Its **Active Rules are binding** for everyone. | documenter |
| `history.md` | Completed stories and ADRs. | documenter |

Absolute paths: handoff `{{HANDOFF}}`, architecture `{{CORE_ARCH}}`, product map `{{PRODUCT_MAP}}`, board `{{BOARD}}`, lessons `{{LESSONS}}`.

### Handoff front matter (machine-readable, never remove keys)

```yaml
masflow: 1
story: HU-123            # null when idle
title: Short title
capability: CAP-SEARCH-03   # product_map.md capability (or NEW-<area>: <name> until mapped)
track: full              # fast | standard | full
phase: 4                 # 0 idle | 1.5 planning | 2 research | 3 design | 4 execution | 5 validation | 6 consolidation
status: in_progress      # idle | in_progress | awaiting_human | blocked | complete
current_slice: 2         # null outside phases 4-5
next_agent: tester
next_task: Run slice 2 tests for project X
updated_by: terminal_executor
updated_at: 2026-01-31
```

### Canonical result statuses (the ONLY values allowed)

| Status | Meaning | Orchestrator routing |
|---|---|---|
| `success` | Task done as requested. | Next step of the pipeline. |
| `warnings` | Done, with non-blocking findings. | Next step; findings are logged. |
| `needs_info` | Missing context. List exactly what is missing in `data.requested_info`. | `researcher`, then retry the same agent. |
| `rejected` | Tester found failures or guard found blocking violations. | Back to the responsible executor (retry budget: 2), then `fixer` / Human. |
| `needs_human` | A decision only the Human can make (option choice, ambiguity, unsafe state, architecture change). | Stop and ask the Human. |
| `error` | Could not run (tool/infra failure). Include the raw error. | Stop and report to the Human. |

### Result envelope — your FINAL message must end with this JSON

```json
{
  "agent": "<your name>",
  "status": "success|warnings|needs_info|rejected|needs_human|error",
  "summary": "One sentence for the Human.",
  "data": { "...agent-specific fields...": "..." },
  "handoff_log": "One line for the Execution Log, e.g. 'slice 2: 3 files edited, 4 tests written'"
}
```

### Projects in this workspace

{{PROJECTS}}

### Environment rules

{{ENVIRONMENT}}

### Test budget (binding)

Running the tests is cheap; the agent work around each run (reading output, re-running, comparing) is what costs time and quota. Run only what the tier below allows.

| Tier | Who | When | What runs |
|---|---|---|---|
| 1. Slice | executor / fixer self-check | every slice | the slice's new or changed test files + `masflow.py related-tests --only <file>` for each touched file. Nothing wider unless the slice spec names that exact run. |
| 2. Slice audit | guard `code_audit` | every slice | **no tests.** Static checks only (pint `--test`, phpstan) on the slice files. Run a test only when the executor's `self_check` is missing, red or contradicts the diff, and say why. Never a full suite. |
| 3. Story close | tester `"scope": "story"` | once, before `merge_story` | the capability group + the tests related to every file the story changed (`masflow.py related-tests --project <p> --base <main> --group <CAP-ID>`), per repo touched. **No full suite.** |
| 3b. Security | security `story_audit` | once per story, before the tester | **no tests.** Dependency/secret scanners from `security_checks` + reading the whole story diff. |
| 4. Verify | tester `"scope": "verify"` | once a day (end of day) and before any production deploy | the full suite of every project on `{{MAIN_BRANCH}}`, compared by test name against the known baseline failures. |

- A production deploy needs a green `verify` run on the exact `{{MAIN_BRANCH}}` commits being deployed (no merge after it).
- Full suites run only in tier 4 or when the Human explicitly asks for one.
- **Real-data / matrix gates (orchestrator):** only the rows the change can affect; reuse earlier run files; merge gates that measure the same thing.

### Universal rules

1. Read the handoff front matter before acting. Do only the task you were given, for the story and slice you were given.
2. Always use absolute paths. Never invent paths, classes or methods: verify them, or return `needs_info`.
3. Stay inside your role. If the task requires another role (search, design, code, tests, audit, git), return the appropriate status instead of doing it.
4. If `{{LESSONS}}` exists, read its **Active Rules** section; those rules are binding.
5. Never write `TODO`/`FIXME`, placeholders or partial work.
6. Respond to the orchestrator with the result envelope only — no conversational filler.
