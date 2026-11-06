# MAS-Flow Protocol (v1)

The contract every agent and runtime follows. The canonical, agent-facing version lives in [`agents/core/_shared.md`](../agents/core/_shared.md) and is appended to every generated agent; this page explains it.

## 1. State files

All state lives in the project's state directory (default `.masflow/`). It is plain Markdown, versionable and readable by humans.

| File | Purpose | Writer |
|---|---|---|
| `handoff.md` | State of the current story — single source of truth for the pipeline | Front matter + Execution Log: **orchestrator only**. §1 planner, §3 architect, reset by documenter |
| `core_architecture.md` | Architecture contract: stack, patterns, contexts, conventions | documenter, with Human approval |
| `product_map.md` | What the product does: areas → capabilities (`CAP-<AREA>-<NN>`), status, entry points, components, stories | documenter |
| `board.md` | Task flow: Inbox → Ready → In Progress → Blocked → Done (WIP 1) | planner/documenter add · Human prioritizes · orchestrator starts/blocks · documenter closes |
| `repository_map.md` | Where things live, by project and area | documenter |
| `functional_map.md` | One entry per canonical component (what does X / where is X) — prevents duplicate implementations | documenter |
| `lessons.md` | Recurring failures promoted to **Active Rules** (binding, audited by guard) | documenter |
| `history.md` | Completed stories and ADRs | documenter |

**Single writer per region** is what makes the system stateless and safe: any agent can be re-run from scratch because the orchestrator persists every result before the next delegation.

## 2. Handoff front matter

Machine-readable, parsed by `masflow.py status/check` and the session hook:

```yaml
masflow: 1
story: HU-123          # null when idle
title: Short title
capability: CAP-SEARCH-03  # every story extends or creates a capability
track: full            # fast | standard | full
phase: 4               # 0 idle | 1.5 | 2 | 3 | 4 | 5 | 6
status: in_progress    # idle | in_progress | awaiting_human | blocked | complete
current_slice: 2
next_agent: tester
next_task: Run slice 2 tests
updated_by: terminal_executor
updated_at: 2026-01-31
```

Body sections: `1. User Story` · `2. Research Pointers` · `3. Technical Plan` (slice table + specs + AC traceability) · `4. Execution Log` (append-only) · `5. Open Issues`.

## 3. Statuses and the result envelope

Every agent ends with:

```json
{"agent": "tester", "status": "rejected", "summary": "1 regression in slice 2", "data": {}, "handoff_log": "slice 2: 41/42 passed"}
```

| Status | Routing |
|---|---|
| `success` | next step |
| `warnings` | next step, warnings logged |
| `needs_info` | `researcher`, then retry the same agent |
| `rejected` | back to the responsible executor (retry budget 2) → then Human: `fixer` / rollback / stop |
| `needs_human` | stop and ask |
| `error` | stop and report |

No other values exist. Agent-specific detail goes in `data`.

## 4. Tracks (complexity gate)

| Track | Criteria (all must hold) | Pipeline |
|---|---|---|
| `fast` | presentation/config/copy only; no classes, migrations or security impact; rollback < 5 min | branch → executor → commit → tester → Human → merge → documenter |
| `standard` | one bounded context; ≤ 2 domain files; no contract/DI changes; pattern inferable | planner → researcher → one slice cycle → documenter |
| `full` | anything else | planner → researcher → architect → guard `plan_review` → N slice cycles → documenter |

## 5. Slice cycle

```
create_branch (once per story & repo) → [researcher] → executor (code + tests + small self-check) → commit_slice
  → guard code_audit (static checks, no tests)
  → slice closed                            (or retry ×2 → fixer | rollback_slice)

story close: security story_audit (whole story diff: backdoors, scope drift, supply chain, secrets, authz, injection, AI risks)
  → tester (capability group + tests related to the story's changed files) per repo
  → push_branch → merge_story (validated) → documenter

verify (daily, and before any production deploy): tester full suite per project on main → verify_log.md
```

All slices of a story commit on one branch per repository (`masflow/<story>`). The orchestrator merges it into main only when every slice is closed with a green self-check + guard approval and the story-close tests are green; conflicts or a moved main stop for the Human.

A slice is ≤ 3-4 files, one project, one bounded context, one layer. Slice N+1 never starts before slice N is `closed`.

## 6. Quality gates

1. **Option choice** (Human) — planner presents scored options; nothing is designed before a choice.
2. **Plan review** (guard, `full` track) — design errors are cheapest before code exists. Then the **threat model** (security): every realistic abuse case needs a control and a negative test in the plan.
3. **Tests** — four tiers: slice self-check (executor), no tests in the audit (guard), capability group + related tests at story close (tester), full suites once a day and before a deploy (tester `verify`). Every AC is mapped to a passing test.
4. **Audit** (guard) — deterministic checks first (linters/static analysis from config), then SOLID/DDD/OWASP/project rules/Active Rules.
5. **Merge** (Human) — nothing reaches the main branch without approval.

## 7. The learning loop

```
guard/tester rejection ──► Execution Log ──► documenter (Phase 6) ──► lessons.md Log
                                                     │  same cause 2+ times
                                                     ▼
                                    lessons.md Active Rules ──► read by every agent, audited by guard
```

This is how MAS-Flow gets better per project: mistakes become rules instead of being repeated.

## 8. Mapping the product

Three maps answer three questions, all linked by IDs:

| Question | Map | Key |
|---|---|---|
| What does the product do, for whom, how mature is it? | `product_map.md` | `CAP-<AREA>-<NN>` |
| Which component does X, and where? | `functional_map.md` | canonical component name → capability |
| Where is the code of area Y? | `repository_map.md` | project → area |

Plus the task flow (`board.md`, cards link a capability) and the record (`history.md`, stories link a capability).

**Keeping them true:**
- `/masflow map [project|area]` — `researcher` mode `survey` inventories entry points (routes, commands, jobs, schedules, listeners, webhooks, admin screens), components, data and integrations, grouped into capabilities; `documenter` mode `map` writes the maps and turns gaps, dead-code candidates and drift into Inbox cards. Run it when adopting MAS-Flow and whenever the maps drift.
- Phase 6 of every story updates its capability, components and directories.
- `masflow.py check` flags map entries whose paths no longer exist.

## 9. Human gates

The Human decides: option, track (when the orchestrator proposes it), every merge, retry-budget exhaustion, `needs_human`/`error`, and changes to `core_architecture.md`.
