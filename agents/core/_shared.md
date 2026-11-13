## MAS-FLOW SHARED PROTOCOL (binding for every agent)

### State files — `{{STATE_DIR}}/`

| File | Purpose | Who writes it |
|---|---|---|
| `handoff.md` | State of the current story. Single source of truth for the pipeline. Small on purpose (see Context budgets). | Front matter + Execution Log: **orchestrator only**, through `masflow.py log`. §1 User Story: planner. §3 Technical Plan: architect. Archived and reset by `masflow.py archive-story`. |
| `slices/slice-<id>.md` | The spec of ONE slice. An agent working on a slice reads its file, never the other slices. | architect |
| `core_architecture.md` | Canonical architecture contract (stack, patterns, bounded contexts, rules). | documenter, only with Human approval |
| `product_map.md` | What the product does: areas → capabilities (`CAP-<AREA>-<NN>`) with status, entry points, components, stories. | documenter |
| `board.md` | Task flow of the workspace: Inbox → Ready → In Progress → Blocked → Done. WIP 1. | planner/documenter add to Inbox · orchestrator moves to In Progress/Blocked · documenter moves to Done |
| `repository_map.md` | Where things live, by project and area (never by story). | documenter |
| `functional_map.md` | What does X / where is X: one entry per canonical component. Prevents duplicate implementations. | documenter |
| `lessons.md` | Recurring failures turned into rules. Its **Active Rules are binding** for the roles they name. Also records *Escapes*: defects no gate caught. | documenter |
| `history.md` | Completed stories and ADRs. | documenter |
| `events.jsonl`, `verify_log.md`, `baseline.json`, `archive/` | Machine records: one event per result, verify runs, known failing tests, closed stories. | `masflow.py` only |

Absolute paths: handoff `{{HANDOFF}}`, slice specs `{{SLICES_DIR}}/slice-<id>.md`, architecture `{{CORE_ARCH}}`, product map `{{PRODUCT_MAP}}`, board `{{BOARD}}`, lessons `{{LESSONS}}`.

### Context budgets (binding)

Every agent re-reads the state files on every run, so their size is paid hundreds of times. Write to them accordingly.

{{BUDGETS}}

Read only what your task needs: the front matter, the sections your role names and — for slice work — your slice spec. Never load the whole state directory.

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
next_task: Run the story-close tests for project X
updated_by: guard
updated_at: 2026-01-31
```

### Canonical result statuses (the ONLY values allowed)

| Status | Meaning | Orchestrator routing |
|---|---|---|
| `success` | Task done as requested. | Next step of the pipeline. |
| `warnings` | Done, with non-blocking findings. | Next step; findings are logged. |
| `needs_info` | Missing context. List exactly what is missing in `data.requested_info`. | `researcher`, then retry the same agent. |
| `rejected` | A check, the tester, the guard or the security auditor found blocking problems. | Back to the responsible executor (retry budget: 2), then `fixer` / Human. |
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

### Gates and test budget (binding)

Running a command is cheap; an agent reading, re-running and comparing its output is what costs time and quota. Deterministic work is done by `masflow.py`, and each model gate runs once, where it pays.

| Tier | Who | When | What runs |
|---|---|---|---|
| 1. Slice self-check | executor / fixer | every slice | the slice's new or changed test files + `masflow.py related-tests --only <file>` for each touched file. Nothing wider unless the slice spec names that exact run. |
| 2. Slice checks | `masflow.py checks` (no model) | every slice, after `commit-slice` | the project's deterministic checks (formatter, static analysis, linters) on the slice files. |
| 2b. Slice audit | guard `code_audit` | only high-risk slices (see the guard policy) | reading the slice files. **No tests.** |
| 3. Story close | security `story_audit` + guard `story_audit` + tester `"scope": "story"`, in parallel | once, before `merge-story` | security and guard read the whole story diff (no tests); the tester runs the capability group + the tests related to every file the story changed (`masflow.py related-tests --project <p> --base <main> --group <CAP-ID>`) and the project's acceptance commands, per repo touched. **No full suite.** |
| 4. Verify | `masflow.py verify` (no model) | once a day (end of day) and before any production deploy | the full suite of every project on `{{MAIN_BRANCH}}`, compared by test name with `baseline.json`. The tester only analyses a red or unreadable run. |

- Guard policy: {{GUARD_POLICY}}
- A re-audit after a fix covers the fix diff plus the gate's own open findings, never the whole story again.
- A production deploy needs a green `verify` run on the exact `{{MAIN_BRANCH}}` commits being deployed (no merge after it).
- Full suites run only in tier 4 or when the Human explicitly asks for one.
- **Real-data / matrix gates (orchestrator):** only the rows the change can affect; reuse earlier run files; merge gates that measure the same thing.

### Universal rules

1. Read the handoff front matter before acting. Do only the task you were given, for the story and slice you were given.
2. Always use absolute paths. Never invent paths, classes or methods: verify them, or return `needs_info`.
3. Stay inside your role. If the task requires another role (search, design, code, tests, audit, git), return the appropriate status instead of doing it.
4. If `{{LESSONS}}` exists, read its **Active Rules** section; the rules tagged with your role (or `all`) are binding.
5. Never write `TODO`/`FIXME`, placeholders or partial work.
6. Respond to the orchestrator with the result envelope only — no conversational filler.
