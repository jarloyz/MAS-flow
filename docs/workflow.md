# MAS-Flow Workflow

MAS-Flow uses a **Continuous Flow (Kanban)** model. An **Orchestrator** (an AI session or the Human) routes each step to one agent and persists state in `handoff.md`; the **Human** decides at every gate (option, merge, escalations). The exact contract is in the [Protocol](protocol.md).

## 0. Cartography (on adoption, then when maps drift)
`/masflow map` — the **Researcher** surveys each project/area and the **Documenter** writes `product_map.md` (capabilities), `functional_map.md`, `repository_map.md`, and adds gaps as cards to `board.md`. Every later story links a capability, so the map stays current.

## 1. Ideation and Specification Phase (Human)
1. The **Human** writes a goal or picks a card from `board.md`.
2. The Orchestrator hands it to the **Planner** (or, for a trivial change, proposes the `fast` track to the Human).

## 1.5 Strategic Planning Phase
1. The **Planner** reads `handoff.md`, `core_architecture.md` and `repository_map.md`.
2. It proposes 2-4 scored solution options.
3. **Human Decision:** The Human selects one option; the Planner writes the User Story + Acceptance Criteria into `handoff.md`.
4. The Planner also assigns the **track**: `fast` (cosmetic/config: straight to a single slice, no guard), `standard` (one bounded context: no architect) or `full` (everything else). See the [Protocol](protocol.md).

## 2. Research and Context Phase
1. The **Researcher** (the only agent that searches the codebase) reads `repository_map.md` and `functional_map.md`, then locates the relevant code.
2. It returns verified pointers (paths, symbols, line ranges), boundary leaks, security context and existing equivalents — never code or recommendations.
3. The Orchestrator persists the pointers in `handoff.md` §2.

## 3. Design Phase (`full` track)
1. The **Architect** reads the User Story, the research pointers, `core_architecture.md`, `functional_map.md` and `lessons.md`.
2. It writes a slice plan into `handoff.md`: slices of ≤ 3-4 files (one project, one bounded context, one layer), each with its executor, files, tests and the acceptance criteria it covers (AC traceability table).
3. The **Guard** reviews the plan (`plan_review`). A rejected plan goes back to the Architect before any code is written.

## 4 & 5. Execution and Validation (one slice at a time)
The Architect's plan is divided into numbered slices. Each slice completes the full cycle below before the next one starts:

1. **Terminal Executor** → `create_branch` (`masflow/<HU>`, one branch per story per repository; later slices check it out).
2. **Researcher** → fetches the pointers listed for this slice.
3. **Specialized Executor** → edits files directly on the branch, writes the tests for its code and runs a small self-check (its own tests + the tests related to the files it touched, static checks). If context is missing it returns `needs_info` and goes back to step 2.
4. **Terminal Executor** → `commit_slice`.
5. **Guard** → audits SOLID, DDD boundaries, OWASP and project rules with static checks only (no tests). Rejections go back to the Executor (then commit again).
6. The slice is marked `closed` in `handoff.md` and the next slice starts. After two or more failed rounds, the Human chooses between the **Fixer**, `rollback_slice`, or stopping.

**Story close:** the **Security** auditor first reads the whole story diff of each repository (backdoors, changes outside the plan or to the guardrails, new dependencies, secrets, access control, injection, prompt injection); a critical finding becomes a security-fix slice, a suspected backdoor stops everything for the Human. Then the **Tester** runs the capability's test group plus the tests related to every file the story changed (no full suite) on the story branch of each repository touched, then the **Terminal Executor** runs `push_branch` and `merge_story` (PR + merge into main). Conflicts or a moved main stop for the Human. Then the Documenter consolidates.

**Verify (daily):** `/masflow verify` — the **Tester** runs the full suite of every project on main once, at the end of the day and before any production deploy, and compares failures with the known baseline. Regressions become Inbox cards; a deploy needs a green verify on the exact commits being deployed.

## 6. Consolidation
The **Documenter**, once every slice is merged:
1. Appends the story (decisions, files, rejections) to `history.md`.
2. Updates `repository_map.md` and `functional_map.md`.
3. Turns rejections into `lessons.md` entries; causes seen twice become binding *Active Rules*.
4. Updates the story's capability in `product_map.md`, moves its card to **Done** and adds follow-ups to the **Inbox** of `board.md`.
5. Proposes `core_architecture.md` changes for Human approval.
6. Resets `handoff.md` to the idle template.
