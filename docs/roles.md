# Roles in MAS-Flow

MAS-Flow relies on agents with narrow responsibilities, a set of deterministic commands for everything that needs no model, and a Human who decides at the gates that need judgement. The binding definition of each role is its prompt in [`agents/core/`](../agents/core/).

## 👥 Agentic Roles

### 0. The Orchestrator (Routing Agent)
**Mission:** Move work through the pipeline without doing the work itself.
- Reads the handoff front matter before every decision and routes each task to exactly one agent.
- Runs the mechanical steps itself with `masflow.py` (`git`, `checks`, `verify`, `log`, `archive-story`) — never any other shell command.
- Never writes code, tests, plans or documentation; never fixes what a gate rejected.
- Is the only writer of the handoff front matter and Execution Log, through `masflow.py log`.
- Stops for the Human at: option selection, track confirmation, an epic split, retry-budget exhaustion and every `needs_human`/`error`. The merge is automatic once every gate is green.
- One session per story: the state lives in the state directory, not in the conversation.

### 0.5 The Planner (Strategic Planning Agent, Phase 1.5)
**Mission:** Make the "what" and "why" explicit before anyone spends tokens on the "how".
- Classifies the change into a track (`fast`, `standard`, `full`) that decides how much pipeline it needs.
- Proposes 2-4 solution options scored on DDD impact, SOLID compliance, tech debt, reuse, regression risk, security, agent cost and time-to-value.
- Splits a goal that does not fit one story (the slice budget) into an epic: a first story plus follow-up cards.
- Waits for the Human to select an option, then writes the User Story + Acceptance Criteria into `handoff.md`.
- **Model:** highest-capacity reasoning model — one run per story.

### 1. The Researcher (Research Agent)
**Mission:** Find the facts before anyone proposes solutions.
- The **only** agent that searches the codebase; other agents that lack context return `needs_info` and the Orchestrator routes the request here.
- **Story mode:** verified pointers (paths, symbols, line ranges), existing equivalents, boundary leaks, security context — never code or recommendations.
- **Survey mode** (`/masflow map`): inventories entry points, components, data and integrations of a project or area, grouped into product capabilities.

### 2. The Documenter (Knowledge Keeper)
**Mission:** Keep the memory of the system accurate and small.
- **Phase 6:** history, product/functional/repository maps, board (card → Done).
- **Learning loop:** turns repeated rejections into a deterministic check when a tool can detect them, or into a role-scoped *Active Rule* otherwise; retires and merges rules to keep them inside their budget.
- **Escape mode:** records defects no gate caught (verify regressions, bugs the Human reports), names the gate that should have caught them and what will catch them next time.
- **Map mode** (`/masflow map`): turns survey results into the product map and rebuilds the other maps by area.
- Proposes `core_architecture.md` changes for Human approval.

### 3. The Architect (Design Agent)
**Mission:** Define how the story is built, at contract level.
- Strictly follows `core_architecture.md`.
- Writes the plan (approach, slice table, AC traceability) in the handoff and **one spec file per slice**: files and responsibilities, signatures and schema, named tests, test infrastructure, done-when. No method bodies — the executor writes the code.
- Marks each slice with a **risk** (`low`/`high`) and a **wave** (slices that can run in parallel).
- Returns a proposed split instead of a plan that exceeds the story budget.
- **Model:** highest-capacity reasoning model.

### 4. The Specialized Executors (Execution Agents)
**Mission:** Write the code and its tests within a specific stack.
- One executor per stack (`executor_laravel`, `executor_filament`, `executor_shopify`, project-specific ones) instead of one monolithic agent; stack rules live in the pack, not in the core.
- Receives one slice, reads only its spec and the given pointers, and edits files directly on the story branch.
- **Writes the tests for its own code and runs a restricted self-check**: the slice's tests, the tests related to the files it touched and the project's slice checks. Git is read-only for it; it never commits.

### 5. The Tester (QA Agent)
**Mission:** Prove the story works and broke nothing.
- **Story mode** (story close): the capability's test group, the tests related to every changed file and the project's acceptance commands. Never the full suite.
- **Verify mode:** analyses the regressions that `masflow.py verify` found (which commit range, which story).
- Reports acceptance-criteria coverage. **Never writes tests or code.**

### 6. The Guard (Architecture/Compliance Agent)
**Mission:** Protect system integrity where a tool cannot.
- **`plan_review`** — audits the Architect's plan before any code exists: AC traceability, slice rules, honest risk marks, specs that describe contracts rather than code.
- **`code_audit`** — audits one slice, only when the plan marks it high-risk (or on every slice with `gates.guard_code_audit = always`).
- **`story_audit`** — once per story, on the whole diff: plan conformance, architecture across slices, and the **AC proof** — the independent check that each acceptance criterion is covered by a test that would fail without the behaviour.
- Deterministic checks (formatter, static analysis, linters) are run by `masflow.py checks`, not by the Guard.

### 6.5 The Security Auditor (Adversarial Review Agent)
- **Role:** Assumes the code may be wrong *or hostile* (agents can be steered by prompt injection, poisoned dependencies or hidden instructions) and trusts nothing it did not read itself.
- **Two modes:** `threat_model` (in parallel with the Guard's plan review) lists the realistic abuse cases of the change and requires a control and a negative test for each; `story_audit` (story close) reads the whole story diff of every repository: backdoors and hidden behaviour, changes outside the plan or to the guardrails (CI, hooks, agent config), supply chain, secrets, access control, injection and AI-specific risks. A re-audit after a fix covers only the fix diff.
- **Never fixes.** Critical findings become a fix slice; a suspected intentional backdoor stops the pipeline for the Human.
- **Model:** highest-capacity reasoning model.

### 7. The Fixer (Escalation Agent)
**Mission:** Unblock a slice that the original Executor could not fix.
- Invoked only after an Executor fails twice and the Human chooses it.
- Diagnosis first (root cause, evidence), then the smallest direct fix on the story branch. An architectural root cause goes back to the Human.

### 8. The Terminal Executor (fallback)
A thin wrapper that runs one `masflow.py git` operation and relays its result — only for runtimes where the orchestrator cannot run shell commands itself.

## ⚙️ Deterministic commands (no model)

| Command | Replaces |
|---|---|
| `masflow.py git create-branch · commit-slice · rollback-slice · push-branch · merge-story` | the git agent |
| `masflow.py checks` | the per-slice audit of formatting and static analysis |
| `masflow.py verify` | the tester running full suites and comparing baselines |
| `masflow.py log` | the orchestrator hand-editing the handoff |
| `masflow.py archive-story` | the documenter resetting the handoff |
| `masflow.py check` · `stats` | — (validation, budgets, metrics) |

## 👤 Human Role (Human-in-the-Loop)

### The Human Director
**Mission:** Decide what is built and resolve what the agents cannot.
- Picks the goal and the option, confirms tracks and epic splits.
- Decides when a slice exhausts its retries, when a gate escalates (`needs_human`), and whether known failures become the test baseline.
- Approves production deploys and changes to `core_architecture.md`.
- Can drive the pipeline by hand, one agent at a time (see the [Execution Guide](execution_guide.md)) — the protocol is the same.
