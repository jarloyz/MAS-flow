# Execution Guide: Running MAS-Flow

Since MAS-Flow is a methodology and not a rigid software library, "running" an agent means assigning a specific Persona (System Prompt) to an LLM and feeding it the exact files it needs. 

You can execute MAS-Flow manually in a chat interface (like ChatGPT or Claude), via an AI-powered IDE (like Cursor, Windsurf, or Copilot), or by building a custom script (using LangChain, CrewAI, etc.).

## 1. How to Send Information to Agents (Context Injection)

Agents in MAS-Flow **do not** need the entire project codebase. You send them information by explicitly attaching or providing specific files. This prevents context bloat.

| Agent Role | Files to Provide (Context) |
| --- | --- |
| **Researcher** | `history.md`, User's raw request, Codebase search tools |
| **Documenter** | `history.md`, `handoff.md` (with Researcher's notes) |
| **Architect** | `core_architecture.md`, `handoff.md` (with User Stories) |
| **Executor** | `handoff.md` (Architect's plan), specific source code files |
| **Tester & Guard** | `core_architecture.md`, recently modified source code files |

## 2. Base System Prompts (Personas)

To instantiate an agent, configure your LLM or script with these base system prompts:

### 📐 The Architect
```text
You are the MAS-Flow Architect. 
Your job is to read the User Story in `handoff.md` and the technical constraints in `core_architecture.md`. 
Output a step-by-step technical implementation plan. Do not write the final code. 
Ensure your plan strictly adheres to the design patterns and stack defined in the architecture.
```

### 💻 The Specialized Executor (Example: Laravel/PHP)
```text
You are the MAS-Flow Laravel Specialized Executor. 
Read the step-by-step plan in `handoff.md`. 
Execute ONLY the steps relevant to your stack. Write production-ready code. 
Do not modify the architecture. If you encounter an ambiguity, stop and ask the Orchestrator. 
Update the `handoff.md` status when finished.
```

### 🛡️ The Guard
```text
You are the MAS-Flow Guard. 
Review the recently modified code against the strict rules defined in `core_architecture.md`. 
If a rule is broken (e.g., missing a Repository, violating SOLID, or wrong formatting), output a detailed error log. 
If all rules are respected, output exactly: "APPROVED".
```

## 3. Advancing the Flow (The Human Orchestrator's Job)

The Human Orchestrator drives the process. Here is the step-by-step mechanical execution of a flow:

1. **Invoke:** The Human opens a session with the *Architect* prompt, attaches `core_architecture.md` and `handoff.md`, and requests the plan.
2. **Evaluate:** The Human reads the generated step-by-step plan. 
3. **Commit to Handoff:** If the human approves the plan, they ensure the plan is saved into `handoff.md` (if using an AI IDE with file-writing tools, the agent might do this itself).
4. **Switch Persona:** The Human changes the system prompt to the *Executor*, points it to the newly updated `handoff.md`, and says: *"Execute the plan"*.
5. **Feedback Loop Cycle:** The Human repeats this process for the Tester and Guard. If an agent fails (e.g., the Guard says "Rule Broken"), the Human takes the Guard's error log, goes back to the Executor session, pastes the error, and says: *"Fix this error raised by the Guard"*.
6. **Cleanup:** Once the code is merged, the human manually adds a summary to `history.md` and wipes the contents of `handoff.md` clean for the next task.

## 4. Parallel Execution (Scaling MAS-Flow)

A common question is: *Can I execute multiple tasks or User Stories in parallel?* 

**Yes, through Git Branching.** 

Because `handoff.md` is a physical file in your repository, attempting to run three User Stories simultaneously on the `main` branch would result in file conflicts and confused agents. To scale MAS-Flow for parallel execution:

1. **Create a Branch per Task:** For each User Story, check out a new branch (e.g., `git checkout -b feature/US-045`).
2. **Isolated Handoffs:** Each branch now has its own isolated `handoff.md` file. 
3. **Parallel Orchestration:** You can have an AI session open for `feature/US-045` (working on frontend) and a completely separate AI session for `feature/US-046` (working on backend). The agents won't interfere with each other because they are reading from different branches.
4. **Merge and Sync:** When a branch passes the Guard and Tester, you merge it into `main`. Then, update the `history.md` in `main` so that all future branches inherit the updated historical context.
