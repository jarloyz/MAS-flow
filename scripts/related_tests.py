"""
MAS-Flow related-tests: map changed files to the tests that cover them.

Pure logic, importable, no side effects at import. Git access is injected (`runner`) so unit tests
never touch a real repository.

    changed = changed_files(repo, "origin/main", runner)
    tests = map_tests(changed, list_test_files(repo), reader)
"""
from __future__ import annotations

import glob
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Callable

Runner = Callable[[list[str]], str]
Reader = Callable[[str], str]

SKIP_DIRS = {"vendor", "node_modules", ".git", "storage", "bootstrap"}
PHP_SOURCE_ROOTS = ("app/", "routes/", "database/", "src/")
TEST_PATH = re.compile(r"^(?:tests/|apps/[^/]+/tests/)")
JS_ASSET = re.compile(r"^(apps/[^/]+)/extensions/.+/assets/([^/]+)\.js$")
JS_APP = re.compile(r"^(apps/[^/]+)/")


class GitError(RuntimeError):
    pass


def git_runner(repo: Path) -> Runner:
    def run(args: list[str]) -> str:
        proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise GitError(proc.stderr.strip() or f"git {' '.join(args)} failed")
        return proc.stdout
    return run


def changed_files(repo: Path, base: str, runner: Runner | None = None) -> tuple[list[str], bool]:
    """Union of committed (base...HEAD), unstaged, staged and untracked files (relative, NUL-split).

    Returns (files, base_resolved); base_resolved is False when the base diff failed and was skipped.
    """
    if base.startswith("-"):
        raise ValueError(f"invalid base '{base}': must not start with '-'")
    run = runner or git_runner(repo)
    found: set[str] = set()
    resolved = True
    queries = (
        (["diff", "--name-only", "-z", f"{base}...HEAD"], True),
        (["diff", "--name-only", "-z"], False),
        (["diff", "--name-only", "--cached", "-z"], False),
        (["ls-files", "--others", "--exclude-standard", "-z"], False),
    )
    for args, tolerate in queries:
        try:
            output = run(args)
        except GitError:
            if not tolerate:
                raise
            resolved = False  # unknown base ref: fall back to the working tree only
            continue
        found.update(name for name in output.split("\0") if name)
    return sorted(found), resolved


def normalize_only(repo: Path, only: list[str]) -> tuple[list[str], list[str]]:
    """Make --only values repo-relative (absolute inside the repo, './'-prefixed, plain relative).

    Returns (normalized, ignored); ignored holds the raw values that point outside the repo.
    """
    root = repo.resolve()
    normalized: list[str] = []
    ignored: list[str] = []
    for raw in only:
        path = Path(raw)
        if path.is_absolute():
            try:
                rel = path.resolve().relative_to(root).as_posix()
            except ValueError:
                ignored.append(raw)
                continue
        else:
            rel = os.path.normpath(raw).replace(os.sep, "/")
            if rel == ".." or rel.startswith("../"):
                ignored.append(raw)
                continue
        normalized.append(rel)
    return normalized, ignored


def filter_only(changed: list[str], only: list[str] | None) -> list[str]:
    """Keep changed files equal to or under one of the `only` paths (all files when `only` is None)."""
    if only is None:
        return changed
    prefixes = [o.rstrip("/") for o in only]
    return [c for c in changed if any(c == p or c.startswith(p + "/") for p in prefixes)]


def is_test_file(path: str) -> bool:
    return bool(TEST_PATH.match(path)) and (path.endswith("Test.php") or path.endswith(".test.js"))


def list_test_files(repo: Path) -> list[str]:
    """All test files of the repo (tests/ and apps/*/tests/), relative paths, vendor/node_modules skipped."""
    found: list[str] = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            rel = os.path.relpath(os.path.join(root, name), repo).replace(os.sep, "/")
            if is_test_file(rel):
                found.append(rel)
    return sorted(found)


def is_php_source(path: str) -> bool:
    return path.endswith(".php") and not is_test_file(path) and not TEST_PATH.match(path)


def map_tests(changed: list[str], test_files: list[str], reader: Reader) -> list[str]:
    """Tests related to the changed files: changed tests, <Class>Test.php convention, class references, JS assets."""
    selected: set[str] = {p for p in changed if is_test_file(p)}
    php_tests = [t for t in test_files if t.endswith("Test.php")]
    known = set(test_files)

    for path in changed:
        if is_php_source(path):
            short = Path(path).stem
            word = re.compile(rf"\b{re.escape(short)}\b")
            for test in php_tests:
                if Path(test).name == f"{short}Test.php":
                    selected.add(test)
                elif word.search(reader(test)):
                    selected.add(test)
            continue
        match = JS_ASSET.match(path)
        if match:
            candidate = f"{match.group(1)}/tests/{match.group(2)}.test.js"
            if candidate in known:
                selected.add(candidate)
    return sorted(selected)


def expand_group(repo: Path, patterns: list[str]) -> list[str]:
    """Expand group paths/globs (relative to the repo) into existing files."""
    found: set[str] = set()
    for pattern in patterns:
        for match in glob.glob(pattern, root_dir=repo, recursive=True):
            if (repo / match).is_file():
                found.add(match.replace(os.sep, "/"))
    return sorted(found)


def validate_groups(project: dict, repo: Path) -> list[str]:
    """Problems with projects[].test_groups: every entry a list of strings, each path/glob matching a file."""
    groups = project.get("test_groups")
    name = project.get("name")
    if groups is None:
        return []
    if not isinstance(groups, dict):
        return [f"project {name}: test_groups must be an object of CAP-ID -> list of paths"]
    problems: list[str] = []
    for cap, patterns in groups.items():
        if not isinstance(patterns, list) or not all(isinstance(p, str) for p in patterns):
            problems.append(f"project {name}: test_groups[{cap}] must be a list of strings")
            continue
        for pattern in patterns:
            if not expand_group(repo, [pattern]):
                problems.append(f"project {name}: test_groups[{cap}] path '{pattern}' matches no file")
    return problems


def _php_command(template: str, expand: Callable[[str], str], files: list[str]) -> str:
    """Fill the project's tests.file template with several files: the word holding {file} is repeated per file."""
    out: list[str] = []
    for word in template.split(" "):
        if "{file}" in word:
            strip = "tests/{file}" in word
            for file in files:
                rel = file[len("tests/"):] if strip and file.startswith("tests/") else file
                out.append(shlex.quote(expand(word).replace("{file}", rel)))
        else:
            out.append(expand(word))
    return " ".join(out)


def _container_root(template: str) -> str | None:
    match = re.search(r"(/var/www/[^/\s]+)", template)
    return match.group(1) if match else None


def _sail_prefix(template: str) -> str | None:
    """Host part of a containerized test template, up to the sail binary (`cd X && ./vendor/bin/sail`)."""
    match = re.match(r"^(.*?\bsail)\s+(?:test|artisan\s+test)\b", template.strip())
    return match.group(1) if match else None


def _jest_commands(project: dict, expand: Callable[[str], str], js_tests: list[str]) -> list[str]:
    tests_cfg = project.get("tests", {})
    by_app: dict[str, list[str]] = {}
    for test in js_tests:
        match = JS_APP.match(test)
        by_app.setdefault(match.group(1) if match else "", []).append(test)
    commands = []
    file_template = tests_cfg.get("file", "")
    container = _container_root(file_template)
    sail = _sail_prefix(file_template)
    for app, tests in sorted(by_app.items()):
        rel = " ".join(shlex.quote(t[len(app) + 1:] if app else t) for t in tests)
        if tests_cfg.get("jest"):
            commands.append(expand(tests_cfg["jest"]).replace("{app}", shlex.quote(app)).replace("{files}", rel))
        elif container and sail:
            inner = f"cd {shlex.quote(container + '/' + app if app else container)} && npx jest {rel}"
            commands.append(expand(sail) + " bash -c " + shlex.quote(inner))
        else:
            commands.append(expand("cd {project}") + (f"/{shlex.quote(app)}" if app else "") + f" && npx jest {rel}")
    return commands


def _phpstan_command(project: dict, expand: Callable[[str], str], php_sources: list[str]) -> str | None:
    files = [p for p in php_sources if p.startswith(PHP_SOURCE_ROOTS)]
    if not files:
        return None
    for check in project.get("checks", []):
        if "phpstan" in check:
            base = check.split(" <", 1)[0].strip()
            return f"{expand(base)} {' '.join(shlex.quote(f) for f in files)}"
    return None


def build_commands(project: dict, expand: Callable[[str], str], tests: list[str], changed: list[str]) -> list[str]:
    """One combined PHP test command, jest commands per app and the phpstan command for changed PHP sources."""
    php_tests = [t for t in tests if t.endswith(".php")]
    js_tests = [t for t in tests if t.endswith(".js")]
    commands: list[str] = []
    template = project.get("tests", {}).get("file")
    if php_tests and template:
        commands.append(_php_command(template, expand, php_tests))
    commands += _jest_commands(project, expand, js_tests) if js_tests else []
    phpstan = _phpstan_command(project, expand, [p for p in changed if is_php_source(p)])
    if phpstan:
        commands.append(phpstan)
    return commands


def related(
    project: dict,
    repo: Path,
    expand: Callable[[str], str],
    base: str,
    group: str | None = None,
    runner: Runner | None = None,
    reader: Reader | None = None,
    only: list[str] | None = None,
) -> tuple[dict, int]:
    """Returns ({files_changed, tests, commands, base_resolved} or {error, known_groups}, exit_code).

    `only` must already be repo-relative (see normalize_only); None means no filter. Explicitly named
    existing test files are included even when unchanged.
    """
    read = reader or (lambda path: (repo / path).read_text(encoding="utf-8", errors="replace"))
    if group is not None:
        groups = project.get("test_groups") or {}
        if group not in groups:
            return {"error": f"unknown group '{group}'", "known_groups": sorted(groups)}, 2
        tests = expand_group(repo, groups[group])
        return {
            "files_changed": [], "tests": tests, "commands": build_commands(project, expand, tests, []),
            "base_resolved": True,
        }, 0
    changed, resolved = changed_files(repo, base, runner)
    changed = filter_only(changed, only)
    explicit = [o for o in only or [] if is_test_file(o) and (repo / o).is_file()]
    changed = sorted(set(changed) | set(explicit))
    tests = map_tests(changed, list_test_files(repo), read)
    return {
        "files_changed": changed, "tests": tests, "commands": build_commands(project, expand, tests, changed),
        "base_resolved": resolved,
    }, 0
