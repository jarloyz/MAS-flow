"""
MAS-Flow git operations: the story branch lifecycle as deterministic commands.

Each function runs one operation in one repository and returns a result envelope
(`status`, `summary`, `data`, `handoff_log`) with the same statuses the agents use. Nothing here
rewrites history, forces a push, stashes, discards or resolves conflicts: anything unexpected
stops with `needs_human`.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def envelope(status: str, summary: str, data: dict | None = None, log: str | None = None) -> dict:
    return {"agent": "masflow", "status": status, "summary": summary, "data": data or {}, "handoff_log": log or summary}


def run(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), cwd=str(repo), capture_output=True, text=True, check=False)


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return run(repo, "git", *args)


def out(proc: subprocess.CompletedProcess) -> str:
    return (proc.stdout + proc.stderr).strip()


def current_branch(repo: Path) -> str:
    return git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def branch_exists(repo: Path, branch: str) -> bool:
    return git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}").returncode == 0


def has_origin(repo: Path) -> bool:
    return "origin" in git(repo, "remote").stdout.split()


def porcelain(repo: Path) -> tuple[list[str], list[str]]:
    """(tracked changes, untracked files) from `git status --porcelain`."""
    tracked, untracked = [], []
    for line in git(repo, "status", "--porcelain").stdout.splitlines():
        (untracked if line.startswith("??") else tracked).append(line[3:])
    return tracked, untracked


def relative(repo: Path, files: list[str]) -> list[str]:
    result = []
    for name in files:
        path = Path(name)
        result.append(str(path.resolve().relative_to(repo.resolve())) if path.is_absolute() else name)
    return result


def not_a_repo(repo: Path) -> dict | None:
    if git(repo, "rev-parse", "--git-dir").returncode != 0:
        return envelope("error", f"{repo} is not a git repository", {"repo": str(repo)})
    return None


def wrong_branch(repo: Path, branch: str, command: str) -> dict | None:
    actual = current_branch(repo)
    if actual != branch:
        return envelope("needs_human", f"{command}: expected branch {branch}, repository is on {actual}",
                        {"command": command, "repo": str(repo), "branch": actual})
    return None


# --------------------------------------------------------------------------- commands

def create_branch(repo: Path, branch: str, main: str) -> dict:
    data = {"command": "create_branch", "repo": str(repo), "branch": branch}
    if (bad := not_a_repo(repo)):
        return bad
    tracked, untracked = porcelain(repo)
    data["pending_changes"] = tracked + untracked
    notes: list[str] = []
    if current_branch(repo) == branch:
        return envelope("success", f"already on {branch}", data, f"branch {branch} checked out")
    if tracked:
        return envelope("needs_human", f"working tree has uncommitted changes to tracked files in {repo.name}; "
                        "commit or move them before starting the story", data)
    if branch_exists(repo, branch):
        proc = git(repo, "checkout", branch)
    else:
        proc = git(repo, "checkout", main)
        if proc.returncode == 0:
            # branch from the newest main: a stale base only shows up at merge time, after all the work
            if has_origin(repo) and git(repo, "pull", "--ff-only", "origin", main).returncode != 0:
                notes.append(f"could not fast-forward {main} from origin: branched from the local {main}")
            proc = git(repo, "checkout", "-b", branch)
    data["git_output"] = out(proc)
    if proc.returncode != 0:
        return envelope("error", f"could not check out {branch}", data)
    if untracked:
        notes.append(f"{len(untracked)} untracked files left alone")
    return envelope("warnings" if notes else "success", f"on {branch}" + (f" ({'; '.join(notes)})" if notes else ""),
                    data, f"branch {branch} checked out")


def commit_slice(repo: Path, branch: str, story: str, slice_id: str, message: str, files: list[str],
                 formatter=None) -> dict:
    """`formatter(relative_file) -> (ok, output) | None` runs the project's formatter on one file before staging."""
    data = {"command": "commit_slice", "repo": str(repo), "branch": branch, "commit": None}
    if (bad := not_a_repo(repo)) or (bad := wrong_branch(repo, branch, "commit_slice")):
        return bad
    files = relative(repo, files)
    if not files:
        return envelope("error", "commit_slice needs --files", data)
    formatted = []
    for name in files:
        result = formatter(name) if formatter and (repo / name).exists() else None
        if result is not None:
            ok, output = result
            if not ok:
                data["git_output"] = output
                return envelope("rejected", f"formatter failed on {name}", data)
            formatted.append(name)
    proc = git(repo, "add", "-A", "--", *files)
    if proc.returncode != 0:
        data["git_output"] = out(proc)
        return envelope("error", "git add failed", data)
    if git(repo, "diff", "--cached", "--quiet", "--", *files).returncode == 0:
        return envelope("error", "nothing to commit: none of the listed files changed", data)
    # `-- files` commits only the slice: anything the Human had staged before stays staged, out of the commit
    proc = git(repo, "commit", "-m", f"masflow: {story} slice{slice_id} — {message}", "--", *files)
    data["git_output"] = out(proc)[-1500:]
    if proc.returncode != 0:
        return envelope("error", "git commit failed", data)
    data["commit"] = git(repo, "rev-parse", "--short", "HEAD").stdout.strip()
    data["formatted"] = formatted
    tracked, untracked = porcelain(repo)
    data["pending_changes"] = tracked + untracked
    status = "warnings" if tracked else "success"
    summary = f"slice {slice_id} committed as {data['commit']}" + (f"; {len(tracked)} other tracked changes left uncommitted" if tracked else "")
    return envelope(status, summary, data, f"slice {slice_id}: commit {data['commit']} ({len(files)} files)")


def rollback_slice(repo: Path, branch: str, commits: list[str]) -> dict:
    data = {"command": "rollback_slice", "repo": str(repo), "branch": branch, "commit": None}
    if (bad := not_a_repo(repo)) or (bad := wrong_branch(repo, branch, "rollback_slice")):
        return bad
    if not commits:
        return envelope("error", "rollback_slice needs --commits (newest first)", data)
    proc = git(repo, "revert", "--no-edit", *commits)
    data["git_output"] = out(proc)[-1500:]
    if proc.returncode != 0:
        git(repo, "revert", "--abort")
        return envelope("needs_human", "revert did not apply cleanly (aborted, nothing changed)", data)
    data["commit"] = git(repo, "rev-parse", "--short", "HEAD").stdout.strip()
    return envelope("success", f"reverted {len(commits)} commit(s)", data, f"rollback: reverted {', '.join(commits)}")


def push_branch(repo: Path, branch: str) -> dict:
    data = {"command": "push_branch", "repo": str(repo), "branch": branch}
    if (bad := not_a_repo(repo)) or (bad := wrong_branch(repo, branch, "push_branch")):
        return bad
    tracked, _ = porcelain(repo)
    if tracked:
        data["pending_changes"] = tracked
        return envelope("needs_human", "tracked files have uncommitted changes; the pushed branch would not match what was validated", data)
    if not has_origin(repo):
        return envelope("warnings", "no `origin` remote: nothing pushed (local-only repository)", data, f"push skipped: {repo.name} has no remote")
    proc = git(repo, "push", "-u", "origin", branch)
    data["git_output"] = out(proc)[-1500:]
    if proc.returncode != 0:
        return envelope("needs_human", "push rejected (never forced)", data)
    return envelope("success", f"pushed {branch}", data, f"pushed {branch}")


def merge_story(repo: Path, branch: str, main: str, story: str, title: str, body: str = "",
                validated: bool = False, use_gh: bool = True) -> dict:
    data = {"command": "merge_story", "repo": str(repo), "branch": branch, "commit": None, "pr_url": None}
    if not validated:
        return envelope("needs_human", "merge_story needs --validated: run it only after every gate of the story close is green", data)
    if (bad := not_a_repo(repo)):
        return bad
    tracked, _ = porcelain(repo)
    if tracked:
        data["pending_changes"] = tracked
        return envelope("needs_human", "tracked files have uncommitted changes; refusing to merge", data)
    if not branch_exists(repo, branch):
        return envelope("error", f"branch {branch} does not exist", data)
    remote = has_origin(repo)
    upstream = f"origin/{main}" if remote else main

    if remote:
        proc = git(repo, "fetch", "origin")
        if proc.returncode != 0:
            data["git_output"] = out(proc)
            return envelope("error", "git fetch failed", data)
        local = git(repo, "rev-parse", branch).stdout.strip()
        pushed = git(repo, "rev-parse", "--verify", "--quiet", f"origin/{branch}").stdout.strip()
        if local != pushed:
            return envelope("needs_human", f"{branch} differs from origin/{branch}: run push_branch first", data)
    if git(repo, "merge-base", "--is-ancestor", upstream, branch).returncode != 0:
        return envelope("needs_human", f"{upstream} moved since the story branched: the story must be re-validated on top of it", data)

    title_line = f"{story}: {title}"
    if remote and use_gh and shutil.which("gh") and run(repo, "gh", "auth", "status").returncode == 0:
        created = run(repo, "gh", "pr", "create", "--base", main, "--head", branch, "--title", title_line, "--body", body or title_line)
        if created.returncode == 0:
            data["pr_url"] = created.stdout.strip().splitlines()[-1] if created.stdout.strip() else None
        elif "already exists" not in out(created):
            data["git_output"] = out(created)[-1500:]
            return envelope("needs_human", "gh pr create failed", data)
        merged = run(repo, "gh", "pr", "merge", branch, "--merge", "--delete-branch")
        if merged.returncode != 0:
            data["git_output"] = out(merged)[-1500:]
            return envelope("needs_human", "gh pr merge failed (conflicts or branch protection)", data)
        steps = [("checkout", main), ("pull", "--ff-only", "origin", main)]
    else:
        steps = [("checkout", main)]
        if remote:
            steps.append(("pull", "--ff-only", "origin", main))
        steps.append(("merge", "--no-ff", branch, "-m", f"feat: {story} — {title}"))
        if remote:
            steps.append(("push", "origin", main))

    for step in steps:
        proc = git(repo, *step)
        if proc.returncode != 0:
            data["git_output"] = out(proc)[-1500:]
            if step[0] == "merge":
                data["conflicts"] = [l[3:] for l in git(repo, "status", "--porcelain").stdout.splitlines()
                                     if l[:2] in ("UU", "AA", "DU", "UD")]
                git(repo, "merge", "--abort")
            if step[0] != "push" and branch_exists(repo, branch):
                git(repo, "checkout", branch)  # leave the repository where the story was, not half-way on main
            if step[0] == "merge":
                return envelope("needs_human", "merge conflict (aborted, nothing merged)", data)
            if step[0] == "push":
                return envelope("needs_human", f"merged locally into {main} but `git push origin {main}` failed (never forced): "
                                "push it by hand", data)
            return envelope("needs_human", f"git {' '.join(step)} failed (never forced)", data)

    data["commit"] = git(repo, "rev-parse", "--short", "HEAD").stdout.strip()
    if remote and branch_exists(repo, branch):
        git(repo, "push", "origin", "--delete", branch)
    if branch_exists(repo, branch):
        git(repo, "branch", "-d", branch)
    return envelope("success", f"{story} merged into {main} as {data['commit']}", data, f"merged {branch} into {main} ({data['commit']})")
