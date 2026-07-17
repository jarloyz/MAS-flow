# Roles in MAS-Flow

The MAS-Flow methodology relies on an ecosystem of agents with hyper-specific responsibilities, all orchestrated by the Human Director.

## 👥 Agentic Roles (Artificial Intelligence)

### 1. The Researcher (Research Agent)
**Mission:** Understand the problem before proposing solutions.
- Analyzes new requirements provided by the user.
- Inspects the existing codebase and dependencies.
- **Deliverable:** Writes conclusions in the `handoff.md` file.

### 2. The Documenter / Analyst (Documentation Agent)
**Mission:** Translate findings into executable tasks and maintain historical context.
- Reads the history of previously completed User Stories (US) and the currently modified files to understand the project's state.
- **Map Maintenance:** Maintains the `repository_map.md` (a lightweight index of the codebase) so the Researcher doesn't have to read thousands of lines of code.
- Designs clear, granular User Stories for the current iteration with verifiable Acceptance Criteria.
- **Model Recommendation:** Can use a faster, cost-effective model as it primarily formats and structures information.

### 3. The Architect (Planning Agent)
**Mission:** Define and propose the technical strategy based on the specific tech stack.
- **Owns the Architecture:** Reads and strictly adheres to the `core_architecture.md` file. 
- Designs a step-by-step technical implementation plan.
- **Model Recommendation:** Requires a high-capacity reasoning model (e.g., Claude 3.5 Sonnet, GPT-4o).

### 4. The Specialized Executors (Execution Agents)
**Mission:** Write the code and build the solution within a specific domain.
- **Specialization:** Instead of one monolithic agent, you have multiple specialized executors (e.g., `Laravel PHP Executor`, `Python Video Processing Executor`).
- This reduces prompt complexity, lowers token consumption, and prevents syntax mixing.
- Receives the step-by-step plan from the Architect and executes only the steps relevant to its domain.
- **Structural Tagging:** Must include architectural tags (e.g., `@domain`, `@layer`) in DocBlocks/Comments. This allows the Guard to audit code without reading every line of implementation.

### 5. The Tester (QA Agent)
**Mission:** Guarantee the code works.
- Reviews the Executor's code, creates, and runs tests.
- If it fails, writes an error log for the human orchestrator to review.

### 6. The Guard (Architecture/Compliance Agent)
**Mission:** Protect system integrity.
- Audits the final code against the rules defined in `core_architecture.md` (e.g., SOLID, DDD).
- Scans architectural tags (DocBlocks) and structural patterns rather than reading every line of implementation, saving tokens and improving accuracy.
- Flags architectural violations.

### 7. The DevOps / Terminal Executor
**Mission:** Handle system-level operations and environment setup.
- Executes shell commands, package installations (e.g., `npm install`, `composer require`), and database migrations.
- If an Executor needs a new external library, this agent is invoked to install it and configure the local environment safely.
- Heavily relies on Model Context Protocol (MCP) servers to securely interact with the local machine.

---

## 👤 Human Role (Human-in-the-Loop)

### The Human Orchestrator / Director
**Mission:** Actively guide the flow, evaluate outputs, and coordinate the agents.
- **Calls Agents Manually:** The human triggers each agent one by one (e.g., running the Researcher, then reviewing its output, then running the Documenter).
- **Evaluates Steps:** At each handoff, the human verifies that the result is correct.
- **Course Correction:** If an agent fails or hallucinated, the human steps in, corrects the `handoff.md`, or uses a specialized "Correction Agent" to fix the issue before passing it to the next step.
- Updates the `core_architecture.md` when the project evolves (which inherently updates the context for all agents).
