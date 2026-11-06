#!/usr/bin/env python3
"""
Claude Code PreToolUse(Bash) hook for MAS-Flow.

Blocks commands whose program is listed in masflow.config.json -> command_guard.blocked
(e.g. host `php`/`composer` when everything must run inside a container) and tells the model
what to run instead (command_guard.hint). Exit code 2 = block and show stderr to the model.
"""
import json
import os
import re
import shlex
import sys
from pathlib import Path


def load_guard() -> dict:
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    for directory in (root, *root.parents):
        config = directory / "masflow.config.json"
        if config.exists():
            try:
                return json.loads(config.read_text(encoding="utf-8")).get("command_guard", {})
            except (OSError, json.JSONDecodeError):
                return {}
    return {}


SEPARATORS = {"&&", "||", ";", "|", "&", "(", ")", ";;"}


def command_segments(command: str) -> list[list[str]]:
    """Split a shell command into simple commands, respecting quotes (quoted text is data, not a command)."""
    segments: list[list[str]] = []
    heredocs: list[tuple[str, bool]] = []  # pending (delimiter, quoted) whose body starts on the next line
    for line in command.splitlines():
        if heredocs:
            delimiter, quoted = heredocs[0]
            if line.strip() == delimiter:
                heredocs.pop(0)
            elif not quoted:
                # an unquoted heredoc body is data, but its substitutions still execute
                for inner in re.findall(r"\$\(([^()]*)\)|`([^`]*)`", line):
                    segments += command_segments(inner[0] or inner[1])
            continue
        heredocs += [(m.group(2), bool(m.group(1))) for m in re.finditer(r"<<-?\s*(['\"]?)(\w+)\1", line)]
        # command substitutions execute even inside double quotes: inspect them as commands too
        for inner in re.findall(r"\$\(([^()]*)\)|`([^`]*)`", line):
            segments += command_segments(inner[0] or inner[1])
        try:
            lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
            lexer.whitespace_split = True
            tokens = list(lexer)
        except ValueError:  # unbalanced quotes: fall back to a naive split
            tokens = re.split(r"\s+|(&&|\|\||;|\|)", line)
            tokens = [t for t in tokens if t]
        current: list[str] = []
        for token in tokens:
            if token in SEPARATORS:
                segments.append(current)
                current = []
            else:
                current.append(token)
        segments.append(current)
    return [s for s in segments if s]


def main() -> int:
    guard = load_guard()
    blocked = set(guard.get("blocked", []))
    if not blocked:
        return 0
    try:
        command = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    except json.JSONDecodeError:
        return 0

    for words in command_segments(command):
        while words and (re.match(r"^\w+=", words[0]) or words[0] in {"sudo", "env", "time", "nohup", "exec"}):
            words.pop(0)
        if not words:
            continue
        program = words[0]
        base = program.rsplit("/", 1)[-1]
        # a bare name matches anywhere in a path (vendor/bin/phpunit); a path entry must match exactly
        if program in blocked or base in blocked:
            print(
                f"MAS-Flow command guard: '{program}' is blocked in this workspace. {guard.get('hint', '')}".strip(),
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
