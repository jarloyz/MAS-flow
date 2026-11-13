"""
MAS-Flow stats: where the time goes and what each gate catches.

Two sources:
  - <state_dir>/events.jsonl, written by `masflow.py log` (one event per agent result): lead time per
    story, runs and rejections per gate.
  - Claude Code subagent transcripts (optional): active time, peak context and runs per agent.
"""
from __future__ import annotations

import collections
import glob
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

IDLE_GAP_SECONDS = 300  # a longer pause inside a transcript is waiting (limits, permissions, sleep), not work
GATES = ("guard", "security", "tester", "masflow")
LOG_LINE = re.compile(r"^- \S+ (?:\S+ )?([\w-]+)(?::[\w-]+)? (success|warnings|needs_info|rejected|needs_human|error)\b")


def parse_time(raw: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------- events

def story_stats(events: list[dict]) -> list[dict]:
    stories: dict[str, dict] = {}
    for event in events:
        story = event.get("story")
        when = parse_time(event.get("ts", ""))
        if not story or when is None:
            continue
        entry = stories.setdefault(story, {"story": story, "track": event.get("track"), "first": when, "last": when,
                                           "events": 0, "rejected": 0, "needs_human": 0, "slices_closed": set()})
        entry["first"], entry["last"] = min(entry["first"], when), max(entry["last"], when)
        entry["track"] = event.get("track") or entry["track"]
        entry["events"] += 1
        entry["rejected"] += event.get("status") == "rejected"
        entry["needs_human"] += event.get("status") == "needs_human"
        if event.get("slice_status") == "closed":
            entry["slices_closed"].add(str(event.get("slice")))
    result = []
    for entry in stories.values():
        result.append({**entry, "lead_hours": round((entry["last"] - entry["first"]).total_seconds() / 3600, 1),
                       "first": entry["first"].isoformat(), "last": entry["last"].isoformat(),
                       "slices_closed": len(entry["slices_closed"])})
    return sorted(result, key=lambda e: e["last"], reverse=True)


def gate_stats(events: list[dict]) -> list[dict]:
    """Runs and rejections per gate: a gate that never rejects is a candidate to run less often."""
    gates: dict[str, collections.Counter] = {}
    for event in events:
        agent = event.get("agent")
        if agent not in GATES or (agent == "masflow" and event.get("mode") not in ("checks", "verify")):
            continue
        name = f"{agent} {event['mode']}" if event.get("mode") else agent
        gates.setdefault(name, collections.Counter())[event.get("status")] += 1
    rows = []
    for name, counts in sorted(gates.items()):
        runs = sum(counts.values())
        rows.append({"gate": name, "runs": runs, "rejected": counts["rejected"], "warnings": counts["warnings"],
                     "needs_human": counts["needs_human"], "reject_rate": round(counts["rejected"] / runs, 2) if runs else 0})
    return rows


def log_stats(handoff_body: str) -> dict:
    """Agent/status counts from Execution Log lines (for stories logged before events.jsonl existed)."""
    agents: collections.Counter = collections.Counter()
    statuses: collections.Counter = collections.Counter()
    for line in handoff_body.splitlines():
        match = LOG_LINE.match(line)
        if match:
            agents[match.group(1)] += 1
            statuses[match.group(2)] += 1
    return {"agents": dict(agents.most_common()), "statuses": dict(statuses.most_common())}


# --------------------------------------------------------------------------- transcripts

def transcripts_dir(workspace: Path, explicit: str | None = None) -> Path | None:
    if explicit:
        return Path(explicit) if Path(explicit).is_dir() else None
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(workspace))
    home = Path.home()
    bases = [Path(os.environ["CLAUDE_CONFIG_DIR"])] if os.environ.get("CLAUDE_CONFIG_DIR") else []
    bases += [home / ".claude", *sorted((home / ".config" / "claude").glob("*")), home / ".config" / "claude"]
    for base in bases:
        candidate = base / "projects" / slug
        if candidate.is_dir():
            return candidate
    return None


def transcript_stats(directory: Path, days: int | None = None) -> dict:
    """Active time, runs, peak context and output tokens per agent type, from subagent transcripts."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days else None
    agents: dict[str, dict] = {}
    for path in glob.glob(str(directory / "**" / "subagents" / "*.jsonl"), recursive=True):
        meta_file = Path(path[: -len(".jsonl")] + ".meta.json")
        try:
            kind = json.loads(meta_file.read_text(encoding="utf-8")).get("agentType", "?") if meta_file.exists() else "?"
        except (OSError, json.JSONDecodeError):
            kind = "?"
        previous = None
        active = idle = 0.0
        peak = 0
        output_tokens: dict[str, int] = {}
        first = None
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                when = parse_time(entry.get("timestamp", ""))
                if when is None:
                    continue
                first = first or when
                if previous is not None:
                    gap = (when - previous).total_seconds()
                    if gap > IDLE_GAP_SECONDS:
                        idle += gap
                    else:
                        active += gap
                previous = when
                message = entry.get("message")
                if entry.get("type") == "assistant" and isinstance(message, dict):
                    usage = message.get("usage") or {}
                    output_tokens[str(message.get("id"))] = usage.get("output_tokens", 0)
                    peak = max(peak, usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
                               + usage.get("cache_creation_input_tokens", 0))
        if first is None or (cutoff and first < cutoff):
            continue
        row = agents.setdefault(kind, {"agent": kind, "runs": 0, "active_s": 0.0, "idle_s": 0.0, "peak": 0, "out": 0})
        row["runs"] += 1
        row["active_s"] += active
        row["idle_s"] += idle
        row["peak"] += peak
        row["out"] += sum(output_tokens.values())
    total = sum(row["active_s"] for row in agents.values()) or 1.0
    rows = [{"agent": row["agent"], "runs": row["runs"], "share": round(row["active_s"] / total, 3),
             "active_min": round(row["active_s"] / 60, 1), "avg_min": round(row["active_s"] / row["runs"] / 60, 1),
             "avg_peak_context": round(row["peak"] / row["runs"]), "avg_output_tokens": round(row["out"] / row["runs"])}
            for row in agents.values()]
    return {"directory": str(directory), "active_hours": round(total / 3600, 1),
            "idle_hours": round(sum(row["idle_s"] for row in agents.values()) / 3600, 1),
            "agents": sorted(rows, key=lambda r: -r["active_min"])}


# --------------------------------------------------------------------------- rendering

def table(headers: list[str], rows: list[list]) -> str:
    cells = [headers] + [[str(c) for c in row] for row in rows]
    widths = [max(len(row[i]) for row in cells) for i in range(len(headers))]
    return "\n".join("  " + "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip() for row in cells)


def render(report: dict) -> str:
    parts = []
    if report.get("stories"):
        parts.append("Stories (from events.jsonl)\n" + table(
            ["story", "track", "lead h", "events", "slices closed", "rejected", "needs_human"],
            [[s["story"], s["track"] or "—", s["lead_hours"], s["events"], s["slices_closed"], s["rejected"], s["needs_human"]]
             for s in report["stories"]]))
    if report.get("gates"):
        parts.append("Gates — runs vs rejections (a gate that never rejects can run less often)\n" + table(
            ["gate", "runs", "rejected", "warnings", "needs_human", "reject rate"],
            [[g["gate"], g["runs"], g["rejected"], g["warnings"], g["needs_human"], f"{g['reject_rate']:.0%}"] for g in report["gates"]]))
    if not report.get("stories") and report.get("log", {}).get("agents"):
        log = report["log"]
        parts.append("Current handoff Execution Log (no events.jsonl yet)\n"
                     + table(["agent", "runs"], [[a, n] for a, n in log["agents"].items()]) + "\n"
                     + table(["status", "count"], [[s, n] for s, n in log["statuses"].items()]))
    transcripts = report.get("transcripts")
    if transcripts:
        parts.append(f"Agent time (Claude Code transcripts, {transcripts['active_hours']} active hours; "
                     f"{transcripts['idle_hours']} h of pauses > 5 min excluded)\n" + table(
            ["agent", "runs", "% time", "avg min", "avg peak ctx", "avg out tok"],
            [[a["agent"], a["runs"], f"{a['share']:.0%}", a["avg_min"], a["avg_peak_context"], a["avg_output_tokens"]]
             for a in transcripts["agents"]]))
    elif "transcripts" in report:
        parts.append("Agent time: no Claude Code transcripts found for this workspace (pass --transcripts <dir>).")
    if report.get("budgets"):
        parts.append("Context budgets exceeded\n" + "\n".join(f"  - {p}" for p in report["budgets"]))
    return "\n\n".join(parts) if parts else "No data yet: events are recorded by `masflow.py log`."
