#!/usr/bin/env python3
"""Assembles context and invokes Codex CLI for plan review, change review, or health check."""
from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

LOG = logging.getLogger("reviewer")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "reviewer_cli": "codex",
    "reviewer_model": "gpt-5.4",
    "timeout_seconds": 600,
    "max_context_chars": 100000,
    "max_log_entries_in_context": 5,
}


def load_config(state_dir: Path) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    path = state_dir / "config.json"
    if path.exists():
        with open(path) as f:
            cfg.update(json.load(f))
    return cfg


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------

def read_if_exists(path: Path, label: str, max_chars: int = 0) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    if max_chars and len(text) > max_chars:
        text = text[:max_chars] + "\n...[truncated]"
    return f"=== {label} ===\n{text}\n\n"


def read_log_tail(state_dir: Path, n: int) -> str:
    path = state_dir / "review_log.jsonl"
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    tail = lines[-n:] if len(lines) > n else lines
    if not tail:
        return ""
    return "=== Recent Review History ===\n" + "\n".join(tail) + "\n\n"


def assemble_prompt(mode: str, state_dir: Path, tool_root: Path, cfg: dict,
                    diff_file: Path | None = None, test_results: Path | None = None,
                    completion_summary: Path | None = None) -> str:
    max_chars = cfg.get("max_context_chars", 100000)
    parts: list[str] = []

    # 1. Reviewer identity
    identity = state_dir / "reviewer_identity.md"
    if not identity.exists():
        identity = tool_root / "references" / "reviewer_identity.md"
    parts.append(read_if_exists(identity, "Reviewer Identity"))

    # 2. Project brief
    parts.append(read_if_exists(state_dir / "project_brief.md", "Project Brief"))

    # 3. Context summary
    parts.append(read_if_exists(state_dir / "context_summary.md", "Context Summary"))

    # 4. Open issues
    parts.append(read_if_exists(state_dir / "open_issues.md", "Open Issues"))

    # 5. Recent log entries
    parts.append(read_log_tail(state_dir, cfg.get("max_log_entries_in_context", 5)))

    # 6. Checklist
    if mode == "plan-review":
        checklist = tool_root / "references" / "review_checklist_plan.md"
    elif mode == "health-check":
        checklist = tool_root / "references" / "review_checklist_health.md"
    else:
        checklist = tool_root / "references" / "review_checklist_change.md"
    parts.append(read_if_exists(checklist, "Review Checklist"))

    # 7. Feature contract (used by both modes)
    parts.append(read_if_exists(state_dir / "feature_contract.json", "Feature Contract"))

    # 8. Mode-specific material
    if mode == "plan-review":
        parts.append(read_if_exists(state_dir / "current_plan.md", "Plan Under Review"))
    elif mode == "health-check":
        # Health check: GPT reads project files via sandbox read access
        parts.append(
            "=== Health Check Mode ===\n"
            "You are performing a comprehensive project health check.\n"
            "Read the project source files systematically. Start from entry points listed in the project brief, "
            "then follow the call graph through the codebase.\n"
            "Evaluate every area in the checklist. Cite specific file:line for all findings.\n"
            "Number each finding with a sequential ID so the user can reference them.\n\n"
        )
    else:
        parts.append(read_if_exists(state_dir / "current_plan.md", "Approved Plan"))
        if completion_summary:
            parts.append(read_if_exists(completion_summary, "Completion Summary"))
        if diff_file:
            parts.append(read_if_exists(diff_file, "Code Diff"))
        if test_results:
            parts.append(read_if_exists(test_results, "Test Results"))

    # 9. Final instruction
    parts.append(
        "=== Instructions ===\n"
        "Review the above material according to the checklist. "
        "Output a single valid JSON object matching the provided output schema. "
        "No text before or after the JSON.\n"
    )

    prompt = "".join(parts)
    if len(prompt) > max_chars:
        LOG.warning("Prompt is %d chars, truncating to %d", len(prompt), max_chars)
        prompt = prompt[:max_chars]
    return prompt


# ---------------------------------------------------------------------------
# Codex CLI invocation
# ---------------------------------------------------------------------------

def heartbeat(process: subprocess.Popen, stop: threading.Event):
    """Log a status line every 15s while the subprocess runs."""
    start = time.monotonic()
    while not stop.wait(15):
        elapsed = int(time.monotonic() - start)
        LOG.info("Codex still running... %ds elapsed (pid %d)", elapsed, process.pid)


def invoke_codex(prompt: str, mode: str, tool_root: Path, cfg: dict, project_root: Path | None = None) -> str:
    cli = cfg.get("reviewer_cli", "codex")
    model = cfg.get("reviewer_model", "gpt-5.4")
    timeout = cfg.get("timeout_seconds", 600)

    schema_map = {"plan-review": "plan_review_schema.json", "change-review": "change_review_schema.json", "health-check": "health_check_schema.json"}
    schema_name = schema_map[mode]
    schema_path = tool_root / "assets" / schema_name

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as pf:
        pf.write(prompt)
        prompt_file = pf.name

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as of:
        output_file = of.name

    cmd = [
        cli, "exec",
        "--sandbox", "read-only",
        "--model", model,
        "--output-schema", str(schema_path),
        "--ephemeral",
        "-o", output_file,
        "-",  # read prompt from stdin
    ]

    LOG.info("Command: %s", " ".join(cmd))
    LOG.info("Prompt: %d chars, written to %s", len(prompt), prompt_file)
    LOG.info("Output will be written to: %s", output_file)
    LOG.info("Timeout: %ds. GPT reviews typically take 2-4 minutes.", timeout)

    cwd = str(project_root) if project_root else None
    with open(prompt_file) as stdin_f:
        proc = subprocess.Popen(cmd, stdin=stdin_f, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)

    LOG.info("Codex started (pid %d). Waiting for response...", proc.pid)

    stop_evt = threading.Event()
    hb = threading.Thread(target=heartbeat, args=(proc, stop_evt), daemon=True)
    hb.start()

    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise RuntimeError(f"Codex timed out after {timeout}s")
    finally:
        stop_evt.set()
        hb.join(timeout=2)

    LOG.info("Codex finished (exit code %d)", proc.returncode)

    # Log stderr for debugging (Codex prints session info there)
    if stderr:
        stderr_text = stderr.decode(errors="replace").strip()
        if stderr_text:
            for line in stderr_text.splitlines()[:20]:
                LOG.debug("Codex stderr: %s", line)

    # Clean up prompt temp file
    Path(prompt_file).unlink(missing_ok=True)

    if proc.returncode != 0:
        err_msg = stderr.decode(errors="replace").strip() if stderr else "unknown error"
        # Save full error output for debugging
        debug_path = Path(output_file).with_suffix(".debug.txt")
        debug_path.write_text(f"EXIT CODE: {proc.returncode}\n\nSTDERR:\n{err_msg}\n\nSTDOUT:\n{stdout.decode(errors='replace') if stdout else '(empty)'}", encoding="utf-8")
        LOG.error("Debug output saved to %s", debug_path)
        raise RuntimeError(f"Codex exited {proc.returncode}: {err_msg[:500]}")

    # Read output — prefer the output file, fall back to stdout
    out_path = Path(output_file)
    if out_path.exists() and out_path.stat().st_size > 0:
        result = out_path.read_text(encoding="utf-8")
        LOG.info("Read %d chars from output file", len(result))
    else:
        result = stdout.decode(errors="replace") if stdout else ""
        LOG.info("Read %d chars from stdout (output file empty/missing)", len(result))

    out_path.unlink(missing_ok=True)

    if not result.strip():
        raise RuntimeError("Codex returned empty output")
    return result


# ---------------------------------------------------------------------------
# JSON parsing — 3-strategy approach
# ---------------------------------------------------------------------------

def parse_json(raw: str) -> dict:
    # Strategy 1: direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Strategy 2: strip markdown fences
    stripped = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip())
    stripped = re.sub(r"\n?```\s*$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Strategy 3: extract first JSON object via brace matching
    start = raw.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(raw)):
            if raw[i] == "{":
                depth += 1
            elif raw[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[start:i + 1])
                    except json.JSONDecodeError:
                        break

    raise ValueError(f"Could not parse JSON from Codex output (length={len(raw)})")


# ---------------------------------------------------------------------------
# Output handling
# ---------------------------------------------------------------------------

def save_results(result: dict, mode: str, state_dir: Path):
    # Load current state first (needed for task_id in log entry)
    state_path = state_dir / "review_state.json"
    state = {}
    if state_path.exists():
        with open(state_path) as f:
            state = json.load(f)

    # Determine output filename
    out_name_map = {"plan-review": "plan_review.json", "change-review": "change_review.json", "health-check": "health_check.json"}
    out_name = out_name_map[mode]

    # Write review result
    out_path = state_dir / out_name
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    LOG.info("Saved review to %s", out_path)

    # Write paste-back file (plan-review and change-review only)
    paste_back = result.get("paste_back_to_claude", "")
    if paste_back:
        pb_path = state_dir / "paste_back_to_claude.md"
        pb_path.write_text(paste_back, encoding="utf-8")
        LOG.info("Saved paste-back to %s", pb_path)

    # Append to review log
    if mode == "health-check":
        findings = result.get("findings", [])
        critical_findings = [f["description"] for f in findings if f.get("severity") == "critical"]
        verdict = result.get("overall_health", "UNKNOWN")
    else:
        findings = result.get("critical_findings", [])
        critical_findings = findings
        verdict = result.get("verdict", "UNKNOWN")

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": state.get("task_id", ""),
        "mode": mode,
        "verdict": verdict,
        "scores": result.get("scores", {}),
        "key_findings": critical_findings[:3],
        "critical_count": len(critical_findings),
        "context_update": result.get("context_update", ""),
    }
    log_path = state_dir / "review_log.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    LOG.info("Appended log entry to %s", log_path)

    # Update review state
    if mode == "health-check":
        health = result.get("overall_health", "UNKNOWN")
        state["state"] = "health_check_complete"
        state["last_review"] = mode
        state["last_verdict"] = health
    elif mode == "plan-review":
        v = result.get("verdict", "UNKNOWN")
        state["state"] = "plan_approved" if v == "APPROVE" else "plan_pending_review"
        state["last_review"] = mode
        state["last_verdict"] = v
    else:
        v = result.get("verdict", "UNKNOWN")
        state["state"] = "completed" if v == "APPROVE" else "change_pending_review"
        state["last_review"] = mode
        state["last_verdict"] = v
    state["last_review_time"] = datetime.now(timezone.utc).isoformat()

    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)
    LOG.info("Updated state: %s -> %s", mode, state["state"])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Invoke GPT reviewer via Codex CLI")
    parser.add_argument("--mode", required=True, choices=["plan-review", "change-review", "health-check"])
    parser.add_argument("--state-dir", required=True, help="Path to .review/ directory")
    parser.add_argument("--tool-root", default=None, help="Path to the ai-reviewer skill directory")
    parser.add_argument("--project-root", default=None, help="Project root for Codex cwd (health-check)")
    parser.add_argument("--diff-file", default=None, help="Path to diff file (change-review)")
    parser.add_argument("--test-results", default=None, help="Path to test results (change-review)")
    parser.add_argument("--completion-summary", default=None, help="Path to completion summary (change-review)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s %(levelname)s %(message)s")

    state_dir = Path(args.state_dir).resolve()
    if not state_dir.is_dir():
        LOG.error("State directory does not exist: %s", state_dir)
        sys.exit(1)

    # Resolve tool root: explicit arg, or infer from this script's location
    if args.tool_root:
        tool_root = Path(args.tool_root).resolve()
    else:
        tool_root = Path(__file__).resolve().parent.parent  # scripts/ -> ai-reviewer/

    cfg = load_config(state_dir)

    # Resolve optional file paths
    diff_file = Path(args.diff_file).resolve() if args.diff_file else None
    test_results = Path(args.test_results).resolve() if args.test_results else None
    completion_summary = Path(args.completion_summary).resolve() if args.completion_summary else None
    project_root = Path(args.project_root).resolve() if args.project_root else None

    if args.mode == "change-review":
        if not diff_file or not diff_file.exists():
            LOG.error("Change review requires --diff-file pointing to an existing file")
            sys.exit(1)

    # Assemble prompt
    prompt = assemble_prompt(args.mode, state_dir, tool_root, cfg, diff_file, test_results, completion_summary)

    # Invoke Codex
    try:
        raw_output = invoke_codex(prompt, args.mode, tool_root, cfg, project_root)
    except RuntimeError as e:
        LOG.error("Codex invocation failed: %s", e)
        sys.exit(1)

    # Parse result
    try:
        result = parse_json(raw_output)
    except ValueError as e:
        LOG.error("Failed to parse Codex output: %s", e)
        LOG.debug("Raw output: %s", raw_output[:500])
        sys.exit(1)

    # Save outputs and update state
    save_results(result, args.mode, state_dir)

    # Print summary
    if args.mode == "health-check":
        health = result.get("overall_health", "UNKNOWN")
        scores = result.get("scores", {})
        findings = result.get("findings", [])
        print(f"Health: {health}")
        print(f"Scores: {json.dumps(scores)}")
        critical = [f for f in findings if f.get("severity") == "critical"]
        major = [f for f in findings if f.get("severity") == "major"]
        print(f"Findings: {len(findings)} total ({len(critical)} critical, {len(major)} major)")
        for f in critical:
            print(f"  [CRITICAL] #{f.get('id', '?')} {f.get('location', '')}: {f.get('description', '')}")
    else:
        verdict = result.get("verdict", "UNKNOWN")
        scores = result.get("scores", {})
        critical = result.get("critical_findings", [])
        print(f"Verdict: {verdict}")
        print(f"Scores: {json.dumps(scores)}")
        if critical:
            print(f"Critical findings ({len(critical)}):")
            for i, finding in enumerate(critical, 1):
                print(f"  {i}. {finding}")
    print(f"Results saved to {state_dir}")


if __name__ == "__main__":
    main()
