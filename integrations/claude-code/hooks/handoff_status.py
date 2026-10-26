#!/usr/bin/env python3
"""
Claude Code SessionStart hook for MAS-Flow: prints the current pipeline state from handoff.md
so every session starts knowing where the story is. Silent when MAS-Flow is not configured.
"""
import json
import os
from pathlib import Path


def front_matter(text: str) -> dict:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    meta = {}
    for line in text[4:end].splitlines() if end != -1 else []:
        if ":" in line and not line.lstrip().startswith("#"):
            key, value = line.split(":", 1)
            meta[key.strip()] = value.split(" #", 1)[0].strip()
    return meta


def main() -> None:
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    config_file = next((d / "masflow.config.json" for d in (root, *root.parents) if (d / "masflow.config.json").exists()), None)
    if config_file is None:
        return
    try:
        state_dir = json.loads(config_file.read_text(encoding="utf-8")).get("state_dir", ".masflow")
    except json.JSONDecodeError:
        return
    handoff = config_file.parent / state_dir / "handoff.md"
    if not handoff.exists():
        return
    meta = front_matter(handoff.read_text(encoding="utf-8"))
    if not meta:
        print(f"MAS-Flow: {handoff} uses a legacy format (no front matter). Run `python3 MAS-Flow/scripts/masflow.py check`.")
        return
    if meta.get("status") in ("idle", "null", None, ""):
        print("MAS-Flow: no story in progress. Start one with /masflow <goal|card>; see /masflow board.")
        return
    print(
        "MAS-Flow state — "
        f"story {meta.get('story')} ({meta.get('title')}), capability {meta.get('capability')}, track {meta.get('track')}, "
        f"phase {meta.get('phase')}, status {meta.get('status')}, slice {meta.get('current_slice')}. "
        f"Next: {meta.get('next_agent')} — {str(meta.get('next_task')).rstrip('.')}. Continue with /masflow next."
    )


if __name__ == "__main__":
    main()
