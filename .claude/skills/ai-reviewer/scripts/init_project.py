#!/usr/bin/env python3
"""Scan a project and create the .review/ directory with initial state files."""

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

STACK_FILES = {
    "package.json": "Node/JavaScript",
    "pyproject.toml": "Python",
    "setup.py": "Python",
    "requirements.txt": "Python",
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "pom.xml": "Java",
    "Gemfile": "Ruby",
}

KEY_DIRS = {
    "src", "lib", "app", "components", "pages", "api",
    "tests", "scripts", "config", "public", "static",
}

DEFAULT_CONFIG = {
    "reviewer_cli": "codex",
    "reviewer_model": "gpt-5.4",
    "timeout_seconds": 600,
    "max_context_chars": 100000,
    "max_log_entries_in_context": 5,
    "validation_commands": [],
    "language": "auto",
    "max_plan_revisions": 3,
    "max_fix_cycles": 3,
    "install_git_hook": True,
}


def run(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=10)
    return r.stdout.strip() if r.returncode == 0 else ""


def scan_project(root: Path):
    info = {"stacks": [], "deps": [], "key_dirs": [], "readme": "", "ext_counts": Counter(), "branch": "", "commits": []}

    # Tech stack
    for fname, lang in STACK_FILES.items():
        p = root / fname
        if p.exists():
            info["stacks"].append(lang)
            if fname == "package.json":
                try:
                    pkg = json.loads(p.read_text())
                    info["deps"] += list(pkg.get("dependencies", {}).keys())[:5]
                except Exception:
                    pass

    # Key directories
    info["key_dirs"] = sorted(d.name for d in root.iterdir() if d.is_dir() and d.name in KEY_DIRS)

    # README
    readme = root / "README.md"
    if readme.exists():
        info["readme"] = readme.read_text(errors="replace")[:2000]

    # File counts by extension (skip hidden dirs and common large dirs)
    skip_dirs = {".git", "node_modules", "vendor", "__pycache__", ".venv", "venv", "dist", "build", "target"}
    for p in root.rglob("*"):
        if p.is_file() and not any(part in skip_dirs or part.startswith(".") for part in p.parts[len(root.parts):]):
            ext = p.suffix or "(none)"
            info["ext_counts"][ext] += 1

    # Git info
    info["branch"] = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
    log = run(["git", "log", "--oneline", "-5"], cwd=root)
    info["commits"] = log.splitlines() if log else []

    return info


def generate_brief(info):
    overview = info["readme"].split("\n\n")[0].strip() if info["readme"] else "No README found"
    stacks = ", ".join(sorted(set(info["stacks"]))) or "Unknown"
    deps = ", ".join(info["deps"][:5]) or "None detected"
    dirs = ", ".join(f"{d}/" for d in info["key_dirs"]) or "None detected"
    total = sum(info["ext_counts"].values())
    top_ext = ", ".join(f"{c} {e}" for e, c in info["ext_counts"].most_common(10))
    branch = info["branch"] or "Unknown"
    commits = "\n".join(f"  - {c}" for c in info["commits"]) or "  - (no commits)"

    return f"""# Project Brief

## Overview
{overview}

## Tech Stack
- Language: {stacks}
- Key dependencies: {deps}

## Structure
- Key directories: {dirs}
- File count: {total} files ({top_ext})

## Recent Activity
- Branch: {branch}
- Recent commits:
{commits}
"""


def create_review_dir(root: Path, tool_root: Path):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    review = root / ".review"
    review.mkdir(exist_ok=True)

    # Scan and write brief
    info = scan_project(root)
    (review / "project_brief.md").write_text(generate_brief(info))
    print("  Created project_brief.md")

    # Config
    (review / "config.json").write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n")
    print("  Created config.json")

    # Reviewer identity
    src = tool_root / "references" / "reviewer_identity.md"
    if src.exists():
        shutil.copy2(src, review / "reviewer_identity.md")
        print("  Created reviewer_identity.md")
    else:
        print("  WARNING: reviewer_identity.md not found in references/")

    # Review state
    state = {"state": "idle", "task_id": None, "phase": None, "last_verdict": None, "revision_count": 0, "fix_count": 0, "updated_at": now}
    (review / "review_state.json").write_text(json.dumps(state, indent=2) + "\n")
    print("  Created review_state.json")

    # Context summary
    (review / "context_summary.md").write_text(f"""# Reviewer Context Summary
Last updated: {now}

## Project Patterns
(none yet)

## Recurring Issues
(none yet)

## Architectural Decisions
(none yet)

## Recent Reviews
(none yet)
""")
    print("  Created context_summary.md")

    # Open issues
    (review / "open_issues.md").write_text(f"# Open Issues\nLast updated: {now}\n\n(none yet)\n")
    print("  Created open_issues.md")

    # Review log
    (review / "review_log.jsonl").touch()
    print("  Created review_log.jsonl")

    # History dir
    (review / "history").mkdir(exist_ok=True)
    print("  Created history/")

    return DEFAULT_CONFIG


def install_git_hook(root: Path, tool_root: Path):
    hooks_dir = root / ".git" / "hooks"
    if not hooks_dir.exists():
        print("  No .git/hooks/ directory — skipping hook install")
        return
    dest = hooks_dir / "pre-commit"
    if dest.exists():
        print("  WARNING: pre-commit hook already exists — not overwriting")
        return
    src = tool_root / "assets" / "hooks" / "pre-commit-review-gate.sh"
    if not src.exists():
        print("  WARNING: pre-commit-review-gate.sh not found in assets/hooks/")
        return
    shutil.copy2(src, dest)
    dest.chmod(0o755)
    print("  Installed pre-commit hook")


def update_gitignore(root: Path):
    gi = root / ".gitignore"
    marker = ".review/"
    if gi.exists():
        content = gi.read_text()
        if marker in content:
            return
        with gi.open("a") as f:
            f.write(f"\n{marker}\n")
    else:
        gi.write_text(f"{marker}\n")
    print("  Updated .gitignore")


def main():
    parser = argparse.ArgumentParser(description="Initialize .review/ directory for a project")
    parser.add_argument("--project-root", required=True, help="Target project directory")
    parser.add_argument("--tool-root", required=True, help="Skill directory (with references/ and assets/)")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    tool_root = Path(args.tool_root).resolve()

    if not root.is_dir():
        print(f"Error: project root not found: {root}", file=sys.stderr)
        sys.exit(1)
    if not tool_root.is_dir():
        print(f"Error: tool root not found: {tool_root}", file=sys.stderr)
        sys.exit(1)

    print(f"Initializing .review/ in {root}")
    config = create_review_dir(root, tool_root)

    if config.get("install_git_hook"):
        install_git_hook(root, tool_root)

    update_gitignore(root)
    print("Done.")


if __name__ == "__main__":
    main()
