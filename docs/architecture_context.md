# Architecture Context in MAS-Flow

A common pitfall in Multi-Agent Systems is context confusion. To solve this, MAS-Flow introduces the **Core Architecture**, serving as the single source of truth.

## The `core_architecture.md` (and `.json`) File

Every MAS-Flow project must include a `core_architecture.md` file (and optionally a structured `core_architecture.json` for easier programmatic parsing by agents). This file explicitly defines:

1. **Infrastructure:** (e.g., AWS, Docker, Vercel).
2. **Tech Stack & Versions:** (e.g., PHP 8.2, Laravel 11, Python 3.11).
3. **Design Patterns:** (e.g., Domain-Driven Design, Event Sourcing, MVC).
4. **Project-Specific Rules:** (e.g., "Use Python for video processing and PHP for the API").

## Dynamic Agent Updating

The Core Architecture is a living document. **Whenever the developer adds or modifies something in the `core_architecture.md`, the agents must be updated.** 
Because agents load this file at the start of their execution cycle, updating the file inherently updates the agents' knowledge base. 

## How Agents Use It

- **The Architect:** Reads this file before creating the technical implementation plan to ensure the plan fits the ecosystem.
- **The Specialized Executors:** A `Laravel Executor` will use the Core Architecture to know exactly which version of PHP it is targeting, while the `Python Executor` will read it to know which libraries are approved.
- **The Guard:** Uses this file as the strict rulebook to evaluate the final code.
