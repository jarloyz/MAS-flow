# MAS-Flow in Action: A Practical Example

To truly understand how to orchestrate MAS-Flow, let's walk through a concrete example. 
Imagine you (the Human Orchestrator) want to add a new feature: **"Video Uploads with Thumbnail Generation"**. 
Your project uses **Laravel (PHP)** for the API and **Python** for media processing scripts.

Here is how you use AI Assistants (like Gemini, Claude Code, or Cursor) to contextualize your ideas and orchestrate the flow.

## Step 0: Ideation (The Brainstorming)
Before engaging the formal MAS-Flow agents, you use your preferred AI (e.g., Gemini or Claude) purely as a sounding board to clarify your own thoughts.
* **You:** *"I want to add video uploads to my Laravel app. I'm thinking of using a Python script to generate the thumbnail using FFmpeg. Is this a good approach?"*
* **AI:** *"Yes. You can use Laravel's storage to save the raw file, then dispatch a background job that executes your Python FFmpeg script to prevent blocking the API request."*

Now that your idea is clear and contextualized, you start the formal MAS-Flow pipeline.

## Step 1: Context Gathering (The Researcher)
You open a terminal or IDE chat, set the **Researcher** persona, and point it to your workspace.
* **You (Prompt):** *"We need to add Video Uploads. Check our codebase (`history.md` and `/src`) to see how we currently handle media, and write your findings in `handoff.md`."*
* **Researcher Agent:** Scans the code. 
* **Result in `handoff.md`:** 
  > *Researcher Notes: We currently have an `ImageService.php` that uploads to S3. We should create a new `VideoService.php`. The Python scripts live in `/scripts/media/`.*

## Step 2: Task Definition (The Documenter)
You switch the persona to the **Documenter**.
* **You (Prompt):** *"Read the notes in `handoff.md` and create a structured User Story with Acceptance Criteria."*
* **Result in `handoff.md`:** The agent replaces the raw notes with a formal `[US-045] Video Upload Endpoint` ticket.

## Step 3: Technical Strategy (The Architect)
You open a session with a high-reasoning model (like GPT-4o, Gemini Advanced, or Claude 3.5 Sonnet) and set the **Architect** persona. You ensure it reads `core_architecture.md`.
* **You (Prompt):** *"Read US-045 in `handoff.md`. Based on our `core_architecture.md`, write a step-by-step implementation plan in the handoff file."*
* **Result in `handoff.md`:**
  > 1. Create `VideoService.php` (PHP).
  > 2. Create API Endpoint in `VideoController.php` (PHP).
  > 3. Create `generate_thumbnail.py` in `/scripts/media/` (Python).

## Step 4: The Build Phase (Specialized Executors)
Because the plan spans two different technologies, you invoke your Specialized Executors separately. This drastically reduces prompt confusion and token costs.

* **Action 1 (Laravel Executor):** You set the `Laravel Executor` persona.
  * **You (Prompt):** *"Execute Step 1 and 2 from `handoff.md`. Do not touch the Python step."*
  * **Result:** The agent writes the PHP API code flawlessly, adhering to your Laravel structures.
  
* **Action 2 (Python Executor):** You set the `Python Executor` persona.
  * **You (Prompt):** *"Execute Step 3 from `handoff.md`. You only need to write the FFmpeg thumbnail script."*
  * **Result:** The agent writes the perfect Python script.

## Step 5: Quality Assurance (Tester & Guard)
* **Tester Action:** *"Review the new `VideoService.php` and write a PHPUnit test."*
* **Guard Action:** You set the Guard persona, attach `core_architecture.md` and the new files.
  * **You (Prompt):** *"Verify the new PHP and Python files against the core architecture constraints."*
  * **Guard Output:** *"APPROVED. PHP code properly uses Repositories (DDD) and Python code has type hints as required."*

## Step 6: Consolidation
Everything is approved. As the Human Orchestrator:
1. You merge the code into your `main` branch.
2. You copy `[US-045]` from `handoff.md` and paste it at the top of `history.md`.
3. You **delete everything inside `handoff.md`**, leaving it completely blank. The ephemeral context is destroyed, and the system is fresh and ready for US-046.
