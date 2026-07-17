# Core Architecture & Infrastructure

> **Agents**: Read this file to understand the environment you are working in. DO NOT violate the rules and constraints defined here.

## 1. Project Infrastructure
- **Deployment:** [e.g., AWS ECS, Vercel, Docker Compose]
- **CI/CD:** [e.g., GitHub Actions]
- **Database:** [e.g., PostgreSQL 15, Redis for caching]

## 2. Tech Stack & Versions
- **Backend:** [e.g., PHP 8.2, Laravel 11]
- **Frontend:** [e.g., Next.js 14 (App Router), React 18, Tailwind CSS]
- **Scripts/Workers:** [e.g., Python 3.11]

## 3. Design Patterns & Architecture
- **Architecture Type:** [e.g., Domain-Driven Design (DDD) + CQRS]
- **Data Flow:** [e.g., Event Sourcing for critical domain models]
- **State Management:** [e.g., Redux Toolkit on frontend]

## 4. Strict Coding Rules (For Guard & Executors)
- [Rule 1: e.g., All database queries must be executed through Repositories. Controllers cannot use Eloquent directly.]
- [Rule 2: e.g., Python scripts must follow PEP 8 and use Type Hints.]
- [Rule 3: e.g., Ensure 100% test coverage on all Domain Entities.]
- [Rule 4: Structural Tagging. All critical classes and functions MUST include architectural tags (e.g., `@domain [Name]`, `@layer [Name]`) in their DocBlocks to enable fast auditing.]
