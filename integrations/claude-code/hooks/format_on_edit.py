#!/usr/bin/env python3
"""
Claude Code PostToolUse(Edit|Write) hook for MAS-Flow.

When the edited file lives inside a project that declares `format_on_edit` in masflow.config.json
(e.g. "cd {project} && ./vendor/bin/sail bin pint {file}"), runs that command on the file so
formatting never reaches the guard as a finding. `{file}` is the path relative to the project.
`format_on_edit_ext` limits it to some extensions (default: .php, excluding .blade.php).
A failing command (e.g. a syntax error) exits 2 so its output is shown to the model.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

TIMEOUT_SECONDS = 60


def load_config() -> tuple[Path, dict]:
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    for directory in (root, *root.parents):
        config = directory / "masflow.config.json"
        if config.exists():
            try:
                return directory, json.loads(config.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return directory, {}
    return root, {}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    file_path = payload.get("tool_input", {}).get("file_path")
    if not file_path:
        return 0
    file = Path(file_path).resolve()

    workspace, config = load_config()
    for project in config.get("projects", []):
        command = project.get("format_on_edit")
        project_dir = (workspace / project.get("path", ".")).resolve()
        if not command or not file.is_relative_to(project_dir):
            continue
        extensions = project.get("format_on_edit_ext", [".php"])
        if file.name.endswith(".blade.php") or file.suffix not in extensions or not file.exists():
            return 0
        command = (
            command.replace("{workspace}", str(workspace))
            .replace("{project}", str(project_dir))
            .replace("{file}", str(file.relative_to(project_dir)))
        )
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, stdin=subprocess.DEVNULL
            )
        except subprocess.TimeoutExpired:
            print(f"MAS-Flow format_on_edit: timed out after {TIMEOUT_SECONDS}s on {file}", file=sys.stderr)
            return 1
        if result.returncode != 0:
            output = (result.stdout + result.stderr).strip()[-1500:]
            print(f"MAS-Flow format_on_edit failed on {file}:\n{output}", file=sys.stderr)
            return 2
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
