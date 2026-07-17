# MAS-Flow Workflow

MAS-Flow uses a **Continuous Flow (Kanban)** model orchestrated manually by the **Human**. The human evaluates the output at every single step, ensuring maximum quality control.

## 1. Ideation and Specification Phase (Human)
1. The **Human Orchestrator** writes a high-level requirement.
2. The Human manually invokes the **Researcher** agent, feeding it the requirement.

## 2. Research and Context Phase
1. The **Researcher** navigates the repository and reads existing code.
2. It generates the `handoff.md` file with all necessary technical context.
3. **Human Evaluation:** The Human reads the `handoff.md`. If the research is incomplete, the human asks the Researcher to dig deeper or manually edits the file.

## 3. Planning and Architecture Phase
1. The Human invokes the **Documenter** to split the `handoff.md` into User Stories.
2. The Human approves the User Stories.
3. The Human invokes the **Architect** agent.
4. The Architect reads `core_architecture.md` and writes the step-by-step implementation plan into the `handoff.md`.
5. **Human Evaluation:** The Human verifies the architectural plan makes sense for the stack.

## 4. Execution Phase (Specialized)
1. The Human looks at the Architect's plan and decides which **Specialized Executor** to call. 
   - *Example: Step 1 requires a new API endpoint. The Human calls the `Laravel Executor`.*
   - *Example: Step 2 requires a video encoding script. The Human calls the `Python Executor`.*
2. The Executor writes the code and updates the status.
3. **Human Evaluation:** The Human reviews the code diffs. If the code is completely wrong, the Human might invoke a specialized correction agent or fix it manually.

## 5. Validation and Auditing Phase
1. The Human invokes the **Tester** to generate and run unit tests.
2. The Human invokes the **Guard** to ensure the new code didn't violate the `core_architecture.md` rules.
3. If the Guard or Tester flags an issue, the Human Orchestrator sends the specific error back to the relevant Specialized Executor.

## 6. Consolidation
1. Once all tests and guards pass, the Human merges the code.
2. If the architecture changed, the Human updates `core_architecture.md`, immediately updating the baseline knowledge for all agents.
3. The **Documenter** (or Human) updates the `repository_map.md` to reflect any newly created files.
4. The Human appends the User Story to `history.md`.
5. **Handoff Cleanup:** The Human Orchestrator wipes the `handoff.md` file clean. The next iteration will start with a fresh handoff...
