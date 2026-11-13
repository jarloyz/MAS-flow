# MAS-Flow Protocol (v1)

The contract every agent and runtime follows. The canonical, agent-facing version lives in [`agents/core/_shared.md`](../agents/core/_shared.md) and is appended to every generated agent; this page explains it. Where this page and an agent prompt disagree, the prompt in `agents/core/` wins.

## 1. State files

All state lives in the project's state directory (default `.masflow/`). It is plain Markdown and JSON, versionable and readable by humans.

| File | Purpose | Writer |
|---|---|---|
| `handoff.md` | State of the current story — single source of truth for the pipeline | Front matter + Execution Log: **orchestrator only**, through `masflow.py log`. §1 planner, §3 architect |
| `slices/slice-<id>.md` | The spec of one slice (contracts, files, named tests, done-when) | architect |
| `core_architecture.md` | Architecture contract: stack, patterns, contexts, conventions | documenter, with Human approval |
| `product_map.md` | What the product does: areas → capabilities (`CAP-<AREA>-<NN>`), status, entry points, components, stories | documenter |
| `board.md` | Task flow: Inbox → Ready → In Progress → Blocked → Done (WIP 1) | planner/documenter add · Human prioritizes · orchestrator starts/blocks · documenter closes |
| `repository_map.md` | Where things live, by project and area | documenter |
| `functional_map.md` | One entry per canonical component (what does X / where is X) — prevents duplicate implementations | documenter |
| `lessons.md` | **Active Rules** (binding, scoped by role), **Escapes** (defects no gate caught), retired rules, rejection log | documenter |
| `history.md` | Completed stories and ADRs | documenter |
| `events.jsonl` | One machine-readable event per result — the source of `masflow.py stats`. Writes to it and to the handoff are serialized (`.lock`), so results of parallel gates can be logged at the same time | `masflow.py` |
| `baseline.json`, `verify_log.md`, `verify_logs/` | Known failing tests, one line per verify run, raw suite output | `masflow.py verify` |
| `archive/<story>/` | Handoff and slice specs of closed stories | `masflow.py archive-story` |

**Single writer per region** is what makes the system stateless and safe: any agent can be re-run from scratch because the orchestrator persists every result before the next delegation. For the same reason the orchestrator session is disposable: one session per story.

## 2. Handoff front matter

Machine-readable, parsed by `masflow.py status/check` and the session hook, written by `masflow.py log`:

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
next_task: Run the story-close tests
updated_by: guard
updated_at: 2026-01-31
```

Body sections: `1. User Story` · `2. Research Pointers` · `3. Technical Plan` (approach, slice table, AC traceability, risks — the slice specs are separate files) · `4. Execution Log` (append-only, one short line per result) · `5. Open Issues`.

## 3. Context budgets

Every agent re-reads the state files on every run, so their size is paid hundreds of times. Budgets are part of the protocol, configurable in `masflow.config.json → budgets`, and enforced by `masflow.py check` (it fails when one is exceeded):

| Budget | Default | Why |
|---|---|---|
| `story_slices` | 6 | A bigger goal is an epic: the planner splits it into stories. Small stories merge sooner and conflict less. |
| `handoff_kb` / `story_kb` / `plan_kb` | 40 / 6 / 12 KB | The handoff holds state and decisions, not prose. |
| `slice_spec_kb` | 6 KB | A spec names contracts and tests. A bigger one is writing the code twice. |
| `log_line_chars` | 240 | Detail lives in the agent's result, not in the log. |
| `active_rules` / `active_rules_kb` | 30 / 8 KB | Rules are read by every agent forever; graduate them to deterministic checks. |

## 4. Statuses and the result envelope

Every agent — and every `masflow.py` pipeline command — ends with:

```json
{"agent": "tester", "status": "rejected", "summary": "1 regression in the story", "data": {}, "handoff_log": "story: 41/42 passed"}
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

## 5. Tracks (complexity gate)

| Track | Criteria (all must hold) | Pipeline |
|---|---|---|
| `fast` | presentation/config/copy only; no classes, migrations or security impact; rollback < 5 min | branch → executor → commit → checks → story close (security + tester, no guard) → merge → documenter |
| `standard` | one bounded context; ≤ 2 domain files; no contract/DI changes; pattern inferable | planner → researcher → one slice cycle → story close → merge → documenter |
| `full` | anything else | planner → researcher → architect → guard `plan_review` ∥ security `threat_model` → N slice cycles → story close → merge → documenter |

## 6. Slice cycle and story close

```
git create-branch (once per story & repo) → [researcher] → executor (code + tests + self-check)
  → git commit-slice → checks (deterministic, no model)
  → guard code_audit   ONLY on high-risk slices (or every slice with gates.guard_code_audit = always)
  → slice closed                                  (or retry ×2 → fixer | rollback-slice)

story close, in parallel:
    security story_audit  (whole story diff: backdoors, scope drift, supply chain, secrets, authz, injection, AI risks)
    guard    story_audit  (whole story diff: plan conformance, architecture across slices, AC proof)
    tester   scope story  (capability group + tests related to the changed files + acceptance commands)
  → [fix slice `fix-<n>` (not counted in the story size) → only the rejecting gates re-run, on the fix diff]
  → git push-branch → git merge-story → documenter → archive-story

verify (daily, and before any production deploy): masflow.py verify → verify_log.md
    (the tester only analyses a red or unreadable run)
```

- The steps named `git …`, `checks`, `verify` and `archive-story` are **`masflow.py` commands, not agents**: they are deterministic, take seconds and write their own log line.
- All slices of a story commit on one branch per repository (`masflow/<story>`). `create-branch` fast-forwards the main branch from `origin` first, so the story starts from the newest main; `commit-slice` commits only the slice's files, leaving anything the Human had staged out of the commit.
- A slice is ≤ 3-4 files, one project, one bounded context, one layer, with a **risk** (`low`/`high`) and a **wave**. A slice starts only when the slices it depends on are closed; slices of the same wave share no file and may run in parallel when `parallel.slices` > 1.
- The **merge is automatic**: the orchestrator runs `merge-story` without asking, but only when every slice is closed and the three story-close gates are green. Conflicts, a moved main, a rejected push or any doubt stop for the Human. Nothing is ever forced.

## 7. Quality gates

1. **Option choice** (Human) — the planner presents scored options; nothing is designed before a choice.
2. **Plan review** (guard) and **threat model** (security), in parallel, `full` track — design errors are cheapest before code exists. The guard also checks that risk marks are honest and that specs describe contracts, not code.
3. **Self-check** (executor) — the slice's tests and the tests related to the files it touched.
4. **Slice checks** (`masflow.py checks`) — formatter, static analysis, linters on the slice files. No model.
5. **Slice audit** (guard `code_audit`) — only where a mistake is expensive: slices marked high-risk.
6. **Story close** — security, guard and tester in parallel on the whole story. The guard's **AC proof** is the independent verification: the executor wrote both code and tests, so the guard decides, per acceptance criterion, whether its test would fail if the behaviour were removed. The tester also runs the project's **acceptance** commands against the running application.
7. **Verify** (`masflow.py verify`) — full suites daily and before a deploy, compared by test name with `baseline.json`.

Gates are sized by what they catch. `masflow.py stats` shows runs versus rejections per gate: tune `gates.guard_code_audit` and the risk criteria from that data, not from intuition.

## 8. The learning loop

```
rejection (checks / guard / security / tester) ──► Execution Log ──► documenter (Phase 6) ──► lessons.md Log
escape (verify regression, bug found by the Human) ──► documenter (mode escape) ──► lessons.md Escapes
                                                     │  same cause 2+ times
                                                     ▼
                       a tool can detect it? ── yes ──► deterministic check (card CHECK-n → slice_checks, lint rule, test)
                                             └─ no ───► Active Rule, scoped to the roles that can act on it
```

Two things keep the loop healthy. It learns from what the gates **missed**, not only from what they caught: every escape names the gate that should have caught it. And rules do not accumulate: Active Rules have a budget, so adding one beyond it means merging, retiring or graduating another to a check.

## 9. Mapping the product

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

## 10. Human gates

The Human decides: the option, the track (when the orchestrator proposes it), an epic split, retry-budget exhaustion, every `needs_human`/`error` (including a merge that could not complete cleanly), accepting a test baseline, production deploys, and changes to `core_architecture.md`. Everything else runs without waiting.

## 11. Measuring the flow

`masflow.py stats` (or `/masflow stats`) reports, from `events.jsonl` and the runtime's transcripts:

- lead time, events, rejections and Human stops per story;
- runs versus rejections per gate;
- active time, runs, peak context and output size per agent;
- exceeded context budgets.

Change one thing at a time (a gate policy, a budget, a model) and compare before and after.
