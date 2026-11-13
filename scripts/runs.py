"""
MAS-Flow deterministic runs: slice checks and the daily verify.

These steps need no model: run the configured commands, compare the outcome, report. An agent is
only needed afterwards, when something failed and has to be understood.
"""
from __future__ import annotations

import os
import re
import shlex
import signal
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

# Failing test names in the text output of common runners (used when no JUnit report is configured).
FAILURE_PATTERNS = [
    re.compile(r"^\s*\d+\)\s+([\w\\]+::\w+)(?: with data set .*)?\s*$"),   # PHPUnit: "1) Tests\FooTest::test_x"
    re.compile(r"^\s*FAILED\s+(\S+ > .+?)(?:\s{2,}\S+)?\s*$"),            # Laravel/Pest printer: "FAILED  Tests\Foo > name   Exception"
    re.compile(r"^(?:FAILED|ERROR)\s+(\S+::\S+)"),                         # pytest: "FAILED tests/test_x.py::test_y - ..."
    re.compile(r"^\s*●\s+(.+ › .+?)\s*$"),                                 # Jest: "● suite › test name"
]

Shell = Callable[[str, int], tuple[int, str]]
TIMEOUT_CODE = 124


def shell(command: str, timeout: int) -> tuple[int, str]:
    # own process group: on timeout the whole tree is killed, not only the shell (test runners spawn children)
    proc = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            errors="replace", stdin=subprocess.DEVNULL, start_new_session=True)
    try:
        output, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        output, _ = proc.communicate()
        return TIMEOUT_CODE, f"{output or ''}\n[masflow] timed out after {timeout}s"
    return proc.returncode, output or ""


# --------------------------------------------------------------------------- slice checks

def matching_files(check, files: list[str]) -> list[str]:
    if isinstance(check, str):
        return files
    extensions = check.get("ext")
    under = check.get("under")
    return [f for f in files
            if (not extensions or any(f.endswith(e) for e in extensions))
            and (not under or any(f.startswith(u) for u in under))]


def run_checks(project: dict, expand: Callable[[str], str], files: list[str], run: Shell = shell) -> dict:
    """Run projects[].slice_checks on the slice files. Each check is a command with `{files}`, or
    {"run": "...{files}", "ext": [".php"], "under": ["app/"]} to restrict which files it receives."""
    checks = project.get("slice_checks") or []
    if not checks:
        return {"status": "warnings", "summary": f"no slice_checks configured for project {project.get('name')}",
                "data": {"not_configured": True, "checks": [], "manual_checks": [expand(c) for c in project.get("checks", [])]}}
    results = []
    for check in checks:
        selected = matching_files(check, files)
        template = check if isinstance(check, str) else check.get("run", "")
        if not selected:
            results.append({"command": expand(template), "result": "skipped", "output": "no matching files"})
            continue
        command = expand(template).replace("{files}", " ".join(shlex.quote(f) for f in selected))
        code, output = run(command, int(project.get("check_timeout", 600)))
        results.append({"command": command, "result": "pass" if code == 0 else "fail",
                        "output": "" if code == 0 else ANSI.sub("", output).strip()[-2500:]})
    failed = [r for r in results if r["result"] == "fail"]
    return {"status": "rejected" if failed else "success",
            "summary": f"{len(failed)} of {len(results)} slice checks failed" if failed else f"{len(results)} slice checks passed",
            "data": {"checks": results}}


# --------------------------------------------------------------------------- verify

def extract_failures(output: str, patterns: list[re.Pattern] | None = None) -> list[str]:
    found: set[str] = set()
    for line in ANSI.sub("", output).splitlines():
        for pattern in patterns or FAILURE_PATTERNS:
            match = pattern.match(line)
            if match:
                found.add(" ".join(match.group(1).split()))
                break
    return sorted(found)


def junit_failures(path: Path) -> list[str] | None:
    """Failed/errored test names from a JUnit XML report, or None when it cannot be read."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None
    found = set()
    for case in root.iter("testcase"):
        if case.find("failure") is not None or case.find("error") is not None:
            owner = case.get("classname") or case.get("class") or ""
            found.add(f"{owner}::{case.get('name')}" if owner else str(case.get("name")))
    return sorted(found)


def verify_project(project: dict, expand: Callable[[str], str], baseline: list[str], log_file: Path,
                   run: Shell = shell) -> dict:
    tests = project.get("tests", {})
    command = tests.get("verify") or tests.get("full")
    if not command:
        return {"project": project.get("name"), "result": "error", "error": "no tests.full command"}
    junit = Path(expand(tests["junit"])) if tests.get("junit") else None
    if junit is not None and junit.exists():
        junit.unlink()  # a report left by an earlier run must not be read as this run's result
    started = time.monotonic()
    code, output = run(expand(command), int(tests.get("verify_timeout", 3600)))
    duration = round(time.monotonic() - started)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text(output, encoding="utf-8")

    failures = junit_failures(junit) if junit is not None else None
    if failures is None:
        custom = [re.compile(p) for p in tests.get("failure_patterns", [])] or None
        failures = extract_failures(output, custom)
    result = {
        "project": project.get("name"), "command": expand(command), "exit_code": code, "duration_s": duration,
        "log": str(log_file), "failed": failures,
        "regressions": sorted(set(failures) - set(baseline)),
        "baseline_fixed": sorted(set(baseline) - set(failures)),
    }
    if code == TIMEOUT_CODE and "[masflow] timed out" in output:
        result["result"] = "error"
        result["error"] = "the suite timed out (tests.verify_timeout): the failures seen so far are not the whole result"
    elif code != 0 and not failures:
        result["result"] = "error"
        result["error"] = "the suite exited non-zero but no failing test name could be parsed"
    else:
        result["result"] = "red" if result["regressions"] else "green"
    return result
