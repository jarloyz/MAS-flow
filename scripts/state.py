"""
MAS-Flow state operations: the mechanical writes to the handoff that used to cost an agent turn.

Pure text functions (testable without a workspace) plus a few helpers that touch the state directory:
front matter updates, Execution Log lines, slice table rows, the event log, context budgets and
story archiving.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

STATUSES = ("success", "warnings", "needs_info", "rejected", "needs_human", "error")
SLICE_STATUSES = ("pending", "in_progress", "closed", "rolled_back")
SLICE_ID = re.compile(r"^[\w.-]+$")

# Context budgets. Every agent re-reads these files on every run, so their size is paid hundreds of times.
DEFAULT_BUDGETS = {
    "story_slices": 6,       # slices per story; more than this is an epic, split it
    "handoff_kb": 40,        # whole handoff.md
    "story_kb": 6,           # handoff §1 (user story + AC)
    "plan_kb": 12,           # handoff §3 (approach, slice table, AC traceability, risks)
    "slice_spec_kb": 6,      # each slices/slice-<id>.md
    "log_line_chars": 240,   # one Execution Log line
    "active_rules": 30,      # lessons.md Active Rules (count)
    "active_rules_kb": 8,    # lessons.md Active Rules (size)
}

HEADING = re.compile(r"^## (\d+)\. .*$", re.M)


def budgets(config: dict) -> dict:
    return {**DEFAULT_BUDGETS, **(config.get("budgets") or {})}


# --------------------------------------------------------------------------- front matter

def yaml_scalar(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    if text in ("", "null", "true", "false", "~") or re.search(r"[:#\[\]{}\"',|>&*!%@`]|^\s|\s$|^-", text):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def update_front_matter(text: str, updates: dict) -> str:
    """Replace (or append) keys in the YAML front matter, keeping the order and the other lines."""
    if not text.startswith("---\n"):
        raise ValueError("handoff has no front matter")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError("handoff front matter is not closed")
    lines = text[4:end].split("\n")
    pending = dict(updates)
    for index, line in enumerate(lines):
        key = line.split(":", 1)[0].strip()
        if ":" in line and key in pending:
            lines[index] = f"{key}: {yaml_scalar(pending.pop(key))}"
    lines += [f"{key}: {yaml_scalar(value)}" for key, value in pending.items()]
    return "---\n" + "\n".join(lines) + text[end:]


# --------------------------------------------------------------------------- sections

def sections(body: str) -> dict[str, str]:
    """{'1': text of '## 1. ...', ...} — numbered second-level sections of the handoff."""
    found = list(HEADING.finditer(body))
    return {m.group(1): body[m.start():(found[i + 1].start() if i + 1 < len(found) else len(body))]
            for i, m in enumerate(found)}


def append_log(text: str, line: str) -> str:
    """Append one line to '## 4. Execution Log' (creating the section if it is missing)."""
    match = re.search(r"^## 4\. .*$", text, re.M)
    if match is None:
        return text.rstrip("\n") + f"\n\n## 4. Execution Log\n{line}\n"
    following = re.search(r"^## ", text[match.end():], re.M)
    cut = match.end() + following.start() if following else len(text)
    head = text[:cut].rstrip("\n")
    tail = text[cut:]
    return head + "\n" + line + "\n" + ("\n" + tail if tail else "")


def log_line(day: str, agent: str, status: str, message: str, limit: int) -> str:
    message = " ".join(message.split())
    prefix = f"- {day} {agent} {status} — "
    room = max(limit - len(prefix), 20)
    if len(message) > room:
        message = message[: room - 1].rstrip() + "…"
    return prefix + message


def slice_rows(body: str) -> list[dict]:
    """Rows of the slice table in §3 as dicts keyed by header name."""
    rows: list[dict] = []
    header: list[str] | None = None
    for line in body.splitlines():
        if not line.lstrip().startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = cells if cells and cells[0] == "#" else None
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        rows.append(dict(zip(header, cells)))
    return rows


def set_slice_row(text: str, slice_id: str, updates: dict) -> tuple[str, bool]:
    """Update cells (by header name, e.g. Status/Branch/Retries) of one row of the slice table."""
    lines = text.split("\n")
    header: list[str] | None = None
    for index, line in enumerate(lines):
        if not line.lstrip().startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = cells if cells and cells[0] == "#" else None
            continue
        if cells and cells[0] == str(slice_id):
            for name, value in updates.items():
                if name in header and header.index(name) < len(cells):
                    cells[header.index(name)] = str(value)
            lines[index] = "| " + " | ".join(cells) + " |"
            return "\n".join(lines), True
    return text, False


# --------------------------------------------------------------------------- safe writes

@contextlib.contextmanager
def locked(state_dir: Path):
    """Serialize read-modify-write of the handoff: results of parallel gates are logged at the same time."""
    state_dir.mkdir(parents=True, exist_ok=True)
    with (state_dir / ".lock").open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def write_atomic(path: Path, text: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


# --------------------------------------------------------------------------- events

def append_event(state_dir: Path, event: dict) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    with (state_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def read_events(state_dir: Path) -> list[dict]:
    path = state_dir / "events.jsonl"
    events = []
    for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- budgets

def active_rules(lessons: str) -> str:
    match = re.search(r"^## Active Rules\s*$", lessons, re.M)
    if match is None:
        return ""
    following = re.search(r"^## ", lessons[match.end():], re.M)
    return lessons[match.end(): match.end() + following.start() if following else len(lessons)]


def kb(text: str) -> float:
    return len(text.encode("utf-8")) / 1024


def budget_problems(state_dir: Path, config: dict) -> list[str]:
    limits = budgets(config)
    problems: list[str] = []

    def over(label: str, value: float, key: str, unit: str = " KB", fix: str = "") -> None:
        if value > limits[key]:
            shown = f"{value:.1f}" if unit == " KB" else f"{int(value)}"
            problems.append(f"budget: {label} is {shown}{unit} (budgets.{key} = {limits[key]}){'. ' + fix if fix else ''}")

    handoff = state_dir / "handoff.md"
    if handoff.exists():
        text = handoff.read_text(encoding="utf-8")
        parts = sections(text)
        over("handoff.md", kb(text), "handoff_kb", fix="Slice specs belong in slices/slice-<id>.md, not in the handoff")
        over("handoff §1 User Story", kb(parts.get("1", "")), "story_kb")
        over("handoff §3 Technical Plan", kb(parts.get("3", "")), "plan_kb", fix="Keep only approach, slice table, AC traceability and risks")
        planned = [row for row in slice_rows(parts.get("3", "")) if not str(row.get("#", "")).lower().startswith("fix")]
        over("slices in the story", len(planned), "story_slices", unit="", fix="Split the story (epic) into smaller stories")
        long_lines = [l for l in parts.get("4", "").splitlines() if l.startswith("- ") and len(l) > limits["log_line_chars"]]
        if long_lines:
            problems.append(f"budget: {len(long_lines)} Execution Log lines exceed {limits['log_line_chars']} chars "
                            "(budgets.log_line_chars). Write them with `masflow.py log`")
    for spec in sorted((state_dir / "slices").glob("slice-*.md")) if (state_dir / "slices").is_dir() else []:
        over(f"slices/{spec.name}", kb(spec.read_text(encoding="utf-8")), "slice_spec_kb", fix="Specify contracts and tests, not code")
    lessons = state_dir / "lessons.md"
    if lessons.exists():
        rules = active_rules(lessons.read_text(encoding="utf-8"))
        count = len([l for l in rules.splitlines() if re.match(r"^\s*(?:[-*]|\d+\.)\s+\S", l) and "(none yet)" not in l])
        over("lessons.md Active Rules", count, "active_rules", unit=" rules", fix="Retire, merge or graduate rules to a deterministic check")
        over("lessons.md Active Rules", kb(rules), "active_rules_kb")
    return problems


# --------------------------------------------------------------------------- archive

def archive_story(state_dir: Path, template: str, story: str | None) -> Path:
    """Move handoff.md and slices/ to archive/<story>/ and reset the handoff to the idle template."""
    if not story:
        raise ValueError("the handoff has no story to archive (already idle)")
    safe = re.sub(r"[^\w.-]+", "-", str(story)).strip("-") or "story"
    target = state_dir / "archive" / safe
    if target.exists():
        target = state_dir / "archive" / f"{safe}-{datetime.now():%Y%m%d-%H%M%S}"
    target.mkdir(parents=True)
    shutil.move(str(state_dir / "handoff.md"), str(target / "handoff.md"))
    if (state_dir / "slices").is_dir():
        shutil.move(str(state_dir / "slices"), str(target / "slices"))
    (state_dir / "handoff.md").write_text(template, encoding="utf-8")
    return target
