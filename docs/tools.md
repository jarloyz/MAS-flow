# MAS-Flow Tools and Stack

Since MAS-Flow is a conceptual and methodological framework, it is agnostic to the underlying technology. However, to implement it correctly, certain infrastructure is required.

## 🧠 Recommended Large Language Models (LLMs)
Given the level of autonomy required, it is recommended to use "Reasoning" class or high-capacity models:
- **Executor, Architect, and Guard:** Claude 3.5 Sonnet, GPT-4o, Gemini 1.5 Pro.
- **Documenter and Researcher:** Can operate with faster models if the context is not extremely large.

## ⚙️ Agentic Orchestration Frameworks
To build the Orchestrator and the agents' cycles, you can use:
- **LangGraph / LangChain:** Ideal for cyclical flows (Feedback loops) and persistent state control.
- **CrewAI:** Excellent for declaratively defining roles and delegating tasks (though you'll have to force the asynchronous/Kanban model).
- **Microsoft AutoGen:** Very powerful for direct conversation between the *Tester*, the *Executor*, and the *Guard*.
- **Custom Scripts (Python/Node):** Often, building your own pipeline that reads and writes to `.masflow/handoff.md` is the cleanest way to implement MAS-Flow.

## 📂 State Files (External Memory)
The implementation must have read/write access to the disk (Workspace) to read/modify code and update:
1. `handoff.md`: The communication diary (Markdown).
2. `core_architecture.md`: The single source of truth for the project's tech stack and design patterns.

## 🛡️ Auditing Tools (For the "Guard" and "Tester")
To avoid relying 100% on the LLM, the Guard and Tester can use deterministic tools under the hood:

- **Linters & Static Analyzers:** Tools like PHPStan, ESLint, or SonarQube should be triggered by the Guard before even trying to read the code.
- **Test Runners:** The *Tester* agent must be able to run terminal commands (e.g., `npm test`, `vendor/bin/phpunit`) and read the system output.

## 🔌 Model Context Protocol (MCP)
To truly empower your agents, MAS-Flow highly recommends utilizing the **Model Context Protocol (MCP)**. MCP allows your AI agents to securely connect to local tools and data sources.

- **Terminal Execution:** Use MCP to give the *DevOps / Terminal Executor* the ability to run shell commands safely.
- **Database Access:** Use MCP to let the *Tester* query a local testing database to verify if an action (like creating a user) actually worked.
- **File System/Git:** Use MCP to allow the *Investigador* to quickly scan the `repository_map.md` or git history automatically.

Equipping agents with MCPs transforms them from passive text generators into active system operators.
