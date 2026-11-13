---
masflow: 1
story: null
title: null
capability: null
track: null
phase: 0
status: idle
current_slice: null
next_agent: null
next_task: null
updated_by: null
updated_at: null
---
# MAS-Flow Handoff

> Single source of truth for the CURRENT story. The front matter and the Execution Log are written only by the orchestrator, through `masflow.py log`.
> Keep it small (`masflow.py check` enforces the budgets): slice specs live in `slices/slice-<id>.md`, detail lives in the agents' results.
> `masflow.py archive-story` moves this file and `slices/` to `archive/<story>/` and resets it to this template.

## 1. User Story
_Written by `planner` (Phase 1.5)._

## 2. Research Pointers
_Persisted by the orchestrator from `researcher` results (Phase 2): path, lines, one-line why._

## 3. Technical Plan
_Written by `architect` (Phase 3): approach, slice table (with wave and risk), AC traceability, risks. One spec per slice in `slices/slice-<id>.md`._

## 4. Execution Log
_Append-only, one short line per result, written by `masflow.py log`: `- <date> <agent[:mode]> <status> — <summary>`._

## 5. Open Issues
_Unresolved findings (one line each: gate, severity, file:line, required action) and questions for the Human._
