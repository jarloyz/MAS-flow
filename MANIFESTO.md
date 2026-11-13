# MAS-Flow Manifesto

Our methodology is founded on the following **Agentic Principles**. These principles guide the system's behavior when exact rules or specific prompts fall short.

### 1. The Human is the Director
The Human holds the macro-context: what is built, which option, when to stop. An AI orchestrator (or the Human, step by step) routes the work, but it never decides in the Human's place: it stops at every gate that needs judgement — the option, an epic split, a slice that keeps failing, a merge that is not clean, a deploy. Everything else runs without waiting, because a Human approving what a script can verify is a delay, not a control.

### 2. Ephemeral, Budgeted Context
MAS-Flow avoids the complexity of vector databases by keeping context **small and on disk**. `handoff.md` holds only the current story and is archived when it closes; each slice has its own short spec; the long-term memory is a set of plain files (maps, lessons, history). Every agent re-reads these files on every run, so their size has a budget: context that grows without limit makes every agent slower and less accurate. For the same reason the orchestrator session is disposable — one per story.

### 3. Core Architecture as the Source of Truth
The technical environment is defined in a centralized `core_architecture.md`. It dictates the infrastructure, tech stack and design patterns; every agent reads it, the Architect designs within it and the Guard audits against it. It changes only with the Human's approval.

### 4. Specialized Executors, Stack-Neutral Core
Instead of a single monolithic coding agent, MAS-Flow uses **Specialized Executors** (a Laravel executor, a Shopify executor, your own). Stack knowledge lives in packs and project agents; the core roles and the protocol name no framework and no tool.

### 5. Models Think, Scripts Do
A model is slow, costly and non-deterministic; use it for what needs judgement — planning, design, code, audit. Whatever can be computed is a command: git, formatting and static analysis, running suites and comparing them with a baseline, logging, archiving. Each role runs on the model its decision deserves: the top model where one decision steers a whole story, a small one where the work is mechanical, none where a script will do.

### 6. Independent Verification, Sized by Risk
An agent cannot audit its own work: the Executor's code is checked by tools, audited by the Guard, attacked by the Security auditor and exercised by the Tester. But a gate is worth what it catches. Design is reviewed before code exists, where a mistake is cheapest; cheap deterministic checks run on everything; expensive reading is spent on the slices where a mistake is costly and once on the whole story.

### 7. Measure, Then Tune
The flow records what happened — every result, every rejection, every defect that escaped. Gates, budgets and models are changed because the numbers say so, one at a time, and a rule that a tool can enforce becomes a check instead of one more sentence in a prompt.
