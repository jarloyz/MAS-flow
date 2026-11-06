# Roles in MAS-Flow

The MAS-Flow methodology relies on an ecosystem of agents with hyper-specific responsibilities, all orchestrated by the Human Director.

## 👥 Agentic Roles (Artificial Intelligence)

### 0. The Orchestrator (Routing Agent)
**Mission:** Move work through the pipeline without doing the work itself.
- Reads `handoff.md` before every decision and routes each task to exactly one agent.
- Never writes code, tests, plans or documentation; never fixes what the Tester or Guard rejects.
- Persists results that read-only agents (Researcher, Tester, Guard) return into `handoff.md`.
- Stops for Human approval at the key gates: planner option selection, every slice merge, repeated failures.

### 0.5 The Planner (Strategic Planning Agent, Phase 1.5)
**Mission:** Make the "what" and "why" explicit before anyone spends tokens on the "how".
- Classifies the change into a track (`fast`, `standard`, `full`) that decides how much pipeline it needs.
- For any non-trivial request, proposes 2-4 solution options scored on DDD impact, SOLID compliance, tech debt, regression risk, security, agent cost and time-to-value.
- Waits for the Human to select an option, then writes the User Story + Acceptance Criteria into `handoff.md`.
- **Model Recommendation:** Highest-capacity reasoning model available.

### 1. The Researcher (Research Agent)
**Mission:** Understand the problem before proposing solutions.
- Analyzes new requirements provided by the user.
- Inspects the existing codebase and dependencies.
- **Survey mode** (`/masflow map`): inventories entry points, components, data and integrations of a project or area, grouped into product capabilities.
- It is the **only** agent allowed to search the codebase; other agents that lack context return `needs_info` and the Orchestrator routes the request here.
- **Deliverable:** File paths, class/method names and line ranges as structured JSON (never full code dumps), persisted in `handoff.md`.

### 2. The Documenter / Analyst (Documentation Agent)
**Mission:** Translate findings into executable tasks and maintain historical context.
- Reads the history of previously completed User Stories (US) and the currently modified files to understand the project's state.
- **Map Maintenance:** Maintains the `repository_map.md` (a lightweight index of the codebase) so the Researcher doesn't have to read thousands of lines of code.
- Consolidates every finished story (Phase 6): history, product/functional/repository maps, board (card → Done).
- **Map mode** (`/masflow map`): turns survey results into the product map and rebuilds the other maps by area.
- **Learning loop:** turns tester/guard rejections into `lessons.md` entries and promotes repeated causes to binding *Active Rules*.
- Proposes `core_architecture.md` changes for Human approval.
- **Model Recommendation:** Can use a faster, cost-effective model as it primarily formats and structures information.

### 3. The Architect (Planning Agent)
**Mission:** Define and propose the technical strategy based on the specific tech stack.
- **Owns the Architecture:** Reads and strictly adheres to the `core_architecture.md` file. 
- Designs a step-by-step technical implementation plan divided into **slices**: each slice touches at most 3-4 files, one layer and one bounded context, and names its executor and the files the Researcher must fetch.
- **Model Recommendation:** Requires a high-capacity reasoning model (e.g., Claude 3.5 Sonnet, GPT-4o).

### 4. The Specialized Executors (Execution Agents)
**Mission:** Write the code and build the solution within a specific domain.
- **Specialization:** Instead of one monolithic agent, you have multiple specialized executors (e.g., `Laravel PHP Executor`, `Python Video Processing Executor`).
- This reduces prompt complexity, lowers token consumption, and prevents syntax mixing.
- Receives one slice of the Architect's plan and executes only that slice, editing files directly on the slice branch.
- **Writes the tests for its own code** (e.g. PHPUnit) but never runs them or any shell command.
- **Structural Tagging:** Must include architectural tags (e.g., `@domain`, `@layer`) in DocBlocks/Comments. This allows the Guard to audit code without reading every line of implementation.

### 5. The Tester (QA Agent)
**Mission:** Guarantee the code works.
- Runs the test suite (full or filtered) on the slice branch and detects regressions.
- Reports **acceptance-criteria coverage**: every AC must map to a passing test.
- **Never writes tests or code.** Failures are reported and routed back to the original Executor.

### 6. The Guard (Architecture/Compliance Agent)
**Mission:** Protect system integrity.
- Audits the final code against the rules defined in `core_architecture.md` (e.g., SOLID, DDD).
- Scans architectural tags (DocBlocks) and structural patterns rather than reading every line of implementation, saving tokens and improving accuracy.
- Flags architectural violations.
- **Two modes:** `plan_review` audits the Architect's slice plan before any code exists (`full` track); `code_audit` runs deterministic checks (linters, static analysis) first and then audits each slice.

### 6.5 The Security Auditor (Adversarial Review Agent)
- **Role:** Assumes the code may be wrong *or hostile* (agents can be steered by prompt injection, poisoned dependencies or hidden instructions) and trusts nothing it did not read itself.
- **Two modes:** `threat_model` (after the Guard's plan review) lists the realistic abuse cases of the change and requires a control and a negative test for each; `story_audit` (story close, before the Tester and the merge) reads the whole story diff of every repository: backdoors and hidden behaviour, changes outside the plan or to the guardrails (CI, hooks, agent config), supply chain (new or invented packages), secrets, access control, injection and AI-specific risks.
- **Never fixes.** Critical findings become a security-fix slice; a suspected intentional backdoor stops the pipeline for the Human.
- **Model Recommendation:** Highest-capacity reasoning model; it is the slowest gate on purpose.

### 7. The Terminal Executor (Git Branch Manager)
**Mission:** Own the lifecycle of every slice branch.
- `create_branch` (`masflow/<HU>`, one per story per repository) before the first slice in that repo, `commit_slice` after each executor run, `rollback_slice` (revert the slice's commits) after repeated failures, and at story close `push_branch` + `merge_story` once every slice passed Tester + Guard and the final suite is green.
- Can also run environment commands (installs, migrations) when the plan requires them. Never writes application code.

### 8. The Fixer (Escalation Agent)
**Mission:** Unblock a slice that the original Executor could not fix.
- Invoked only after an Executor fails the Tester or Guard two or more times.
- Diagnosis first (reads the failure, reproduces it), then applies the smallest direct fix on the slice branch.

---

## 👤 Human Role (Human-in-the-Loop)

### The Human Orchestrator / Director
**Mission:** Actively guide the flow, evaluate outputs, and coordinate the agents.
- **Calls Agents Manually:** The human triggers each agent one by one (e.g., running the Researcher, then reviewing its output, then running the Documenter).
- **Evaluates Steps:** At each handoff, the human verifies that the result is correct.
- **Course Correction:** If an agent fails or hallucinated, the human steps in, corrects the `handoff.md`, or uses a specialized "Correction Agent" to fix the issue before passing it to the next step.
- Updates the `core_architecture.md` when the project evolves (which inherently updates the context for all agents).
