# MAS-Flow Workflow

MAS-Flow uses a **Continuous Flow (Kanban)** model. An **Orchestrator** (an AI session, or the Human following the same steps) routes each step to one agent or one `masflow.py` command and persists state in `handoff.md`; the **Human** decides at the gates that need judgement (option, epic split, escalations, deploys). The exact contract is in the [Protocol](protocol.md).

Two ideas shape the flow:

- **Models think, scripts do.** Planning, design, coding and auditing go to agents. Git, deterministic checks, the daily verify, logging and archiving are `masflow.py` commands: seconds, no model.
- **Each gate runs once, where it pays.** Design is reviewed before code exists; every slice gets deterministic checks; only high-risk slices get an audit of their own; the whole story is audited and tested once, in parallel, before the merge.

## 0. Cartography (on adoption, then when maps drift)
`/masflow map` — the **Researcher** surveys each project/area and the **Documenter** writes `product_map.md` (capabilities), `functional_map.md`, `repository_map.md`, and adds gaps as cards to `board.md`. Every later story links a capability, so the map stays current.

## 1. Ideation and Specification Phase (Human)
1. The **Human** writes a goal or picks a card from `board.md`.
2. The Orchestrator hands it to the **Planner** (or, for a trivial change, proposes the `fast` track to the Human).

## 1.5 Strategic Planning Phase
1. The **Planner** reads `handoff.md`, `core_architecture.md` and the maps.
2. It proposes 2-4 scored solution options and assigns the **track**: `fast` (cosmetic/config), `standard` (one bounded context, no architect) or `full` (everything else). See the [Protocol](protocol.md).
3. A goal that does not fit one story (more slices than the budget) is an **epic**: each option names the first story and the follow-up stories.
4. **Human Decision:** the Human selects one option; the Planner writes the User Story + Acceptance Criteria into `handoff.md` and the follow-up stories as board cards.

## 2. Research and Context Phase
1. The **Researcher** (the only agent that searches the codebase) reads `repository_map.md` and `functional_map.md`, then locates the relevant code.
2. It returns verified pointers (paths, symbols, line ranges), boundary leaks, security context and existing equivalents — never code or recommendations.
3. The Orchestrator persists the pointers in `handoff.md` §2.

## 3. Design Phase (`full` track)
1. The **Architect** reads the User Story, the research pointers, `core_architecture.md`, `functional_map.md` and `lessons.md`.
2. It writes the plan into `handoff.md` §3 — approach, slice table, AC traceability — and **one spec file per slice** in `slices/`. A slice is ≤ 3-4 files (one project, one bounded context, one layer) with a **risk** mark and a **wave**. Specs describe contracts, files and named tests; the executor writes the code.
3. In parallel, the **Guard** reviews the plan (`plan_review`) and the **Security** auditor writes the threat model. Any rejection goes back to the Architect once, with all findings, before any code is written.

## 4 & 5. Execution and Validation (slice by slice)

1. `masflow.py git create-branch` — `masflow/<HU>`, one branch per story per repository.
2. **Researcher** — only if the slice needs pointers that are not in the handoff yet.
3. **Specialized Executor** — reads its slice spec, edits files directly on the branch, writes the tests for its code and runs a small self-check (its own tests + the tests related to the files it touched). If context is missing it returns `needs_info` and goes back to step 2.
4. `masflow.py git commit-slice` — formats and commits only the slice's files.
5. `masflow.py checks` — the project's deterministic checks (formatter, static analysis, linters) on the slice files. A failure goes back to the Executor.
6. **Guard** `code_audit` — only for slices marked high-risk (authorization, tenant scoping, money, destructive migrations, shared contracts, external input, concurrency). Rejections go back to the Executor.
7. The slice is marked `closed` and the next one starts. After two failed rounds, the Human chooses between the **Fixer**, `rollback-slice`, or stopping.

Slices of the same wave (no shared file, no open dependency) may run in parallel when the config allows it (`parallel.slices`).

**Story close.** Three gates run in parallel on the story branch of each repository touched:
- the **Security** auditor reads the whole story diff (backdoors, changes outside the plan or to the guardrails, new dependencies, secrets, access control, injection, prompt injection);
- the **Guard** reads the whole story diff (`story_audit`): plan conformance, architecture across slices, and the **AC proof** — for every acceptance criterion, would its test fail if the behaviour were removed?
- the **Tester** runs the capability's test group plus the tests related to every file the story changed, and the project's acceptance commands (no full suite).

A critical finding becomes one fix slice, after which only the gates that rejected run again, on the fix diff. A suspected backdoor stops everything for the Human. When all three are green the Orchestrator runs `git push-branch` and `git merge-story` (PR + merge into main) without asking; conflicts or a moved main stop for the Human.

**Verify (daily):** `/masflow verify` runs `masflow.py verify`: the full suite of every project on main, once, compared by test name with `baseline.json`. A regression goes to the Tester (which commit range, which story) and to the Documenter (an *Escape* in `lessons.md`: which gate should have caught it, and what will catch it next time). A deploy needs a green verify on the exact commits being deployed.

## 6. Consolidation
The **Documenter**, once the story is merged:
1. Appends the story (decisions, files, rejections) to `history.md`.
2. Updates `repository_map.md` and `functional_map.md`.
3. Turns repeated rejections into a deterministic check when a tool can detect them, or into a role-scoped *Active Rule* otherwise — keeping the rules inside their budget by merging and retiring.
4. Updates the story's capability in `product_map.md`, moves its card to **Done** and adds follow-ups to the **Inbox** of `board.md`.
5. Proposes `core_architecture.md` changes for Human approval.

Then `masflow.py archive-story` moves the handoff and the slice specs to `archive/<story>/` and resets the handoff. The next story starts in a fresh orchestrator session.

## 7. Measuring
`/masflow stats` shows lead time per story, runs versus rejections per gate, time per agent and exceeded context budgets. Use it to tune the flow: a gate that never rejects can run less often; an agent that takes most of the time is where to look first.
