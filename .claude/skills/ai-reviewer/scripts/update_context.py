#!/usr/bin/env python3
"""Update continuous context after a review cycle completes."""

import argparse, json, shutil, sys
from datetime import datetime, timezone
from pathlib import Path

ARCHIVE_FILES = [
    "current_task.md", "current_plan.md", "feature_contract.json",
    "plan_review.json", "change_review.json", "health_check.json",
    "current_diff.txt", "test_results.txt", "completion_summary.md",
    "paste_back_to_claude.md",
]


def load_json(path):
    return json.loads(path.read_text()) if path.exists() else None


def load_review(state_dir):
    """Load the most recent review: change > health > plan."""
    for name in ("change_review.json", "health_check.json", "plan_review.json"):
        data = load_json(state_dir / name)
        if data:
            return data, name
    return None, None


def update_context_summary(state_dir, task_id, review, task_desc):
    path = state_dir / "context_summary.md"
    text = path.read_text() if path.exists() else "# Context Summary\n\nLast updated: never\n\n## Recent Reviews\n"

    # Update timestamp
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if "Last updated:" in text:
        lines = text.split("\n")
        lines = [l.replace(l, f"Last updated: {now}") if l.startswith("Last updated:") else l for l in lines]
        text = "\n".join(lines)

    # Build entry — handle both review formats
    scores = review.get("scores", {})
    score_str = ", ".join(f"{k}={v}" for k, v in scores.items())
    ctx = review.get("context_update", "None")
    desc = task_desc[:80] if task_desc else "Unknown task"

    if "overall_health" in review:
        # Health check format
        all_findings = review.get("findings", [])
        critical = [f["description"] for f in all_findings if f.get("severity") == "critical"][:3]
        findings_str = "; ".join(critical) if critical else "None"
        verdict_str = review.get("overall_health", "UNKNOWN")
    else:
        findings = review.get("critical_findings", [])[:3]
        findings_str = "; ".join(findings) if findings else "None"
        verdict_str = review.get("verdict", "UNKNOWN")

    entry = (
        f"\n### {task_id}: {desc}\n"
        f"- Verdict: {verdict_str}\n"
        f"- Scores: {score_str}\n"
        f"- Key findings: {findings_str}\n"
        f"- Context update: {ctx}\n"
    )

    if "## Recent Reviews" in text:
        text = text.replace("## Recent Reviews\n", f"## Recent Reviews\n{entry}", 1)
    else:
        text += f"\n## Recent Reviews\n{entry}"

    path.write_text(text)
    print(f"Updated context_summary.md with {task_id}")


def update_open_issues(state_dir, review):
    path = state_dir / "open_issues.md"
    text = path.read_text() if path.exists() else "# Open Issues\n"
    existing = text.lower()

    if "overall_health" in review:
        # Health check: extract critical/major findings as strings
        all_findings = review.get("findings", [])
        findings = [f"{f.get('location', '')}: {f['description']}" for f in all_findings if f.get("severity") in ("critical", "major")]
    else:
        findings = review.get("critical_findings", [])
    verdict = review.get("verdict", "")

    added = 0
    for f in findings:
        if f.lower()[:60] not in existing:
            text += f"- [ ] {f}\n"
            added += 1

    if verdict == "APPROVE":
        changes = [c.lower() for c in review.get("recommended_changes", [])]
        new_lines = []
        resolved = 0
        for line in text.split("\n"):
            stripped = line.strip().lower()
            if stripped.startswith("- [ ]") and any(kw in stripped for kw in changes if len(kw) > 20):
                new_lines.append(line.replace("- [ ]", "- [x]", 1))
                resolved += 1
            else:
                new_lines.append(line)
        text = "\n".join(new_lines)
        if resolved:
            print(f"Resolved {resolved} issue(s) in open_issues.md")

    path.write_text(text)
    if added:
        print(f"Added {added} new issue(s) to open_issues.md")


def archive_task(state_dir, task_id):
    hist = state_dir / "history" / task_id
    hist.mkdir(parents=True, exist_ok=True)
    copied = 0
    for name in ARCHIVE_FILES:
        src = state_dir / name
        if src.exists():
            shutil.copy2(src, hist / name)
            src.unlink()
            copied += 1
    print(f"Archived {copied} file(s) to history/{task_id}/")


def check_context_size(state_dir):
    config = load_json(state_dir / "config.json") or {}
    max_chars = config.get("max_context_chars", 100000)
    summary = state_dir / "context_summary.md"
    if summary.exists() and len(summary.read_text()) > max_chars:
        print(f"WARNING: Context summary exceeds threshold ({max_chars} chars). Manual compression recommended.")


def main():
    parser = argparse.ArgumentParser(description="Update context after review cycle")
    parser.add_argument("--state-dir", required=True, help="Path to .review/ directory")
    parser.add_argument("--task-id", required=True, help="Task identifier e.g. task-20260402-153000")
    args = parser.parse_args()

    state_dir = Path(args.state_dir)
    if not state_dir.is_dir():
        print(f"Error: state dir not found: {state_dir}", file=sys.stderr)
        sys.exit(1)

    review, source = load_review(state_dir)
    if not review:
        print("Error: no review JSON found in state dir", file=sys.stderr)
        sys.exit(1)
    print(f"Using review from {source}")

    task_path = state_dir / "current_task.md"
    task_desc = task_path.read_text().strip().split("\n")[0] if task_path.exists() else ""

    update_context_summary(state_dir, args.task_id, review, task_desc)
    update_open_issues(state_dir, review)
    archive_task(state_dir, args.task_id)
    check_context_size(state_dir)
    print("Context update complete.")


if __name__ == "__main__":
    main()
