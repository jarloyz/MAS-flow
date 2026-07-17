# MAS-Flow Manifesto

Our methodology is founded on the following **Agentic Principles**. These principles guide the system's behavior when exact rules or specific prompts fall short.

### 1. The Human is the Orchestrator and Director
The human developer is not just an observer; they are the active **Orchestrator** of the system. The human calls each agent separately, evaluates that each step provides the correct result, and decides whether to proceed to the next agent or intervene to correct the course. The human holds the macro-context of the project, while the agents only focus on the micro-context.

### 2. Ephemeral Context and Lightweight History
To avoid the complexity of setting up Vector Databases (RAG, Docker, Qdrant), MAS-Flow embraces **Ephemeral Context**. The `handoff.md` is created fresh for each iteration and only contains the necessary information for the *current* task. Once the task is completed, it is wiped clean. However, the system maintains a simple **User Story History** log. This allows agents (like the Documenter) to understand the project's evolution by reading the history of completed tasks and the modified files, without suffering from context bloat.

### 3. Core Architecture as the Source of Truth
The technical environment is defined in a centralized `core_architecture.md` (and optionally a `.json`) file. This file dictates the infrastructure, tech stack, and design patterns. **Whenever the developer updates this core file, the agents must be updated/reloaded** to reflect the new architectural reality.

### 4. Specialized Executors for Reduced Complexity
Instead of a single monolithic coding agent, MAS-Flow utilizes **Specialized Executors**. If a project uses Laravel and Python, there is a dedicated `Laravel Executor` and a `Python Executor`. This reduces token consumption, avoids context confusion, and simplifies the complexity of each agent.

### 5. Multi-Model Ecosystem
Agents are not tied to a single AI model. Each agent uses a model tailored to its complexity. An Architect might use a heavy reasoning model (e.g., GPT-4o or Claude 3.5 Sonnet), while a Documenter or a specialized Python Executor might use a faster, more cost-effective model.

### 6. Strict Separation of Concerns & Independent Verification
An agent cannot audit its own work. Software quality is guaranteed through constructive conflict between specialized roles (Executor, Tester, Guard), all manually orchestrated and ultimately verified by the Human.
