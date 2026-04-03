---
name: ai-reviewer
description: "AI-supervised coding: Claude writes code, GPT reviews via Codex CLI. Three modes: (1) /ai-reviewer <task> — plan review + implementation + completion review, (2) /ai-reviewer check — project health check with findings report, (3) /ai-reviewer status — show workflow state. Also trigger when user mentions 'supervised coding', 'code review by GPT', 'AI review', 'project health check', or wants quality-gated development."
---

# AI Reviewer — Supervised Coding v2

You (Claude) are the **writer and orchestrator**. GPT (via Codex CLI) is the **independent reviewer**.
The reviewer is read-only — it never modifies project files.

## Three Core Functions

| Command | What it does |
|---------|-------------|
| `/ai-reviewer <task>` | Plan → GPT reviews plan → Execute → GPT reviews completion |
| `/ai-reviewer check` | GPT audits the entire project → User picks fixes → Execute → GPT reviews completion |
| `/ai-reviewer init` | Initialize `.review/` for current project |
| `/ai-reviewer status` | Show current workflow state |

## Skill Path

```
SKILL_DIR = <directory containing this SKILL.md>
```

All script paths below are relative to this SKILL_DIR.

---

## Language Boundary

**All `.review/` artifacts are English-only** — plans, reviews, contracts, context, logs.
**User-facing output follows the user's language** — detect from conversation or use `config.json` `"language"` field.
When presenting review results, translate/explain in the user's language. Never translate the artifact files themselves.

---

## Mode Detection

Parse the user's input after `/ai-reviewer`:

1. `init` → **Init**
2. `status` → **Status Check**
3. `check` → **Workflow B: Health Check**
4. Anything else → **Workflow A: Task**

---

## Init

Run once per project, or when user explicitly says `/ai-reviewer init`.

```bash
python3 SKILL_DIR/scripts/init_project.py \
  --project-root "$(pwd)" \
  --tool-root "SKILL_DIR"
```

After the script runs:
1. Read `.review/project_brief.md` and show it to the user
2. Ask: "Does this project brief look correct? Any corrections?"
3. If the user has corrections, update `.review/project_brief.md` accordingly
4. Tell the user: `.review/` has been added to .gitignore

---

# Workflow A: Task (`/ai-reviewer <task>`)

Use this when the user has a specific feature or change to implement.

## A1: Plan Generation

**Pre-check**: If `.review/` doesn't exist, run Init first.

**Pre-check**: Read `.review/review_state.json`. If state is not `idle`, show current state and ask user how to proceed (resume or reset).

1. Generate a task ID: `task-YYYYMMDD-HHMMSS`

2. Write `.review/current_task.md`:
   - The user's task description in English
   - If user wrote in another language, translate to English for the artifact

3. Generate `.review/current_plan.md` — your implementation plan:

   ```markdown
   # Implementation Plan

   ## Goal
   [What this task achieves]

   ## Steps
   1. [Specific, actionable step with file paths]
   2. ...

   ## File Scope
   - Files to modify: [list]
   - Files to create: [list]
   - Files to read (for context): [list]

   ## Risks
   - [Potential issues]

   ## Test Strategy
   - [How to verify the changes work]

   ## Acceptance Criteria
   - [Specific, testable criteria]
   ```

4. Generate `.review/feature_contract.json`:

   ```json
   {
     "task_id": "task-...",
     "task_description": "...",
     "success_criteria": ["..."],
     "constraints": ["..."],
     "scope": { "in_scope": ["..."], "out_of_scope": ["..."] },
     "acceptance_criteria": ["..."],
     "created_at": "ISO 8601"
   }
   ```

5. Update `.review/review_state.json`:
   ```json
   { "state": "plan_pending_review", "task_id": "task-...", "revision_count": 0, "fix_count": 0, "updated_at": "..." }
   ```

6. Show the user the plan and tell them: "Submitting plan to GPT reviewer..."

## A2: Plan Review

Invoke the reviewer:

```bash
python3 SKILL_DIR/scripts/reviewer.py \
  --mode plan-review \
  --state-dir .review/ \
  --tool-root "SKILL_DIR" \
  --project-root "$(pwd)"
```

Read the output from `.review/plan_review.json`.

### Present Results

Show the user:
- **Verdict**: APPROVE / REVISE / BLOCK
- **Scores**: alignment, correctness, maintainability, simplicity, test_readiness (each 0-10)
- **Critical findings**: list each one
- **Recommended changes**: list each one

### Handle Verdict

**APPROVE**:
- Ask user: "Plan approved by reviewer. Proceed with implementation?"
- If user confirms → A3
- Update state: `"state": "plan_approved"`

**REVISE**:
- Read `.review/paste_back_to_claude.md`
- Present the reviewer's revision instructions to the user clearly
- **ASK the user** before making any changes:
  > "The reviewer suggests these changes. How would you like to proceed?
  > 1. Accept all suggestions — I'll revise the plan accordingly
  > 2. Accept with modifications — tell me what to change
  > 3. Reject — keep the plan as-is and proceed to implementation"
- **Wait for user response.** Do NOT auto-apply changes.
- If user accepts (option 1 or 2): apply the revisions to `.review/current_plan.md`, increment `revision_count` in review_state.json, then **proceed directly to A3** (do NOT re-submit to GPT reviewer)
- If user rejects (option 3): proceed to A3 with the current plan unchanged
- Update state: `"state": "plan_approved"`

**BLOCK**:
- Show blocking reasons to user
- Do NOT proceed. Reset state to `idle` or let user decide.

## A3: Execute

**Only enter this phase after plan review is complete + user confirmation.**

1. Update state: `"state": "executing"`

2. **Check working tree**: Run `git status --porcelain` in the project root.
   - If there are uncommitted changes, warn the user:
     > "You have uncommitted changes. I recommend committing or stashing before I start. Shall I proceed anyway?"
   - Wait for user decision. Do NOT auto-commit.

3. **Implement the plan.** You are the writer — make the code changes directly.

4. **Run validations** (if configured in `.review/config.json` `validation_commands`):
   ```bash
   cd <project_root> && <command>
   ```
   Save combined output to `.review/test_results.txt`.

5. **Write completion summary** to `.review/completion_summary.md`:
   This is the natural summary you would normally show the user — what was done, what changed, what files were modified. Just write it as you normally would. Example:
   ```markdown
   ## Completion Summary
   - Added user authentication module in src/auth.py
   - Updated routes in src/api/routes.py to use new auth middleware
   - Fixed config loading bug in src/config.py:42
   - All 3 acceptance criteria addressed
   ```

6. **Collect diff**:
   ```bash
   cd <project_root> && git diff HEAD > .review/current_diff.txt
   ```
   If `current_diff.txt` is empty (all changes are untracked), also run:
   ```bash
   cd <project_root> && git diff --no-index /dev/null <new_files> >> .review/current_diff.txt
   ```

7. Update state: `"state": "change_pending_review"`

8. Tell user: "Implementation complete. Submitting completion report to reviewer..."

## A4: Completion Review

GPT reviews the implementation against the plan and acceptance criteria.

```bash
python3 SKILL_DIR/scripts/reviewer.py \
  --mode change-review \
  --state-dir .review/ \
  --tool-root "SKILL_DIR" \
  --project-root "$(pwd)" \
  --diff-file .review/current_diff.txt \
  --completion-summary .review/completion_summary.md \
  --test-results .review/test_results.txt
```

Read output from `.review/change_review.json`.

### Present Results

Show the user:
- Verdict, scores, critical findings, recommended changes
- Acceptance criteria checks (each criterion: met/not met with evidence)

### Handle Verdict

**APPROVE**:
- Tell user: "Changes approved by reviewer."
- Proceed to Wrap-up

**REVISE**:
- Read `.review/paste_back_to_claude.md`
- Present the reviewer's revision instructions to the user clearly
- **ASK the user** before making any changes:
  > "The reviewer suggests these fixes. How would you like to proceed?
  > 1. Accept all suggestions — I'll apply the targeted fixes
  > 2. Accept with modifications — tell me what to change
  > 3. Reject — keep the code as-is and proceed to completion"
- **Wait for user response.** Do NOT auto-apply changes.
- If user accepts (option 1 or 2): make targeted fixes (fix only what was flagged, do NOT re-implement everything), update `.review/completion_summary.md` with what was fixed, re-collect diff, increment `fix_count`, then **proceed directly to Wrap-up** (do NOT re-submit to GPT reviewer)
- If user rejects (option 3): proceed to Wrap-up

**BLOCK**:
- Show blocking reasons
- Do NOT mark task as complete. Let user decide next steps.

---

# Workflow B: Health Check (`/ai-reviewer check`)

Use this when the user wants a comprehensive audit of an existing project.

## B1: Health Check

**Pre-check**: If `.review/` doesn't exist, run Init first.

1. Generate a task ID: `check-YYYYMMDD-HHMMSS`

2. Write `.review/current_task.md`:
   ```markdown
   Project health check requested by user.
   ```

3. Update state: `"state": "health_check", "task_id": "check-..."}`

4. Tell user: "Starting project health check. GPT will analyze your codebase — this typically takes 3-5 minutes..."

5. Invoke the reviewer:

```bash
python3 SKILL_DIR/scripts/reviewer.py \
  --mode health-check \
  --state-dir .review/ \
  --tool-root "SKILL_DIR" \
  --project-root "$(pwd)"
```

6. Read output from `.review/health_check.json`.

### Present Results

Show the user:
- **Overall health**: HEALTHY / NEEDS_ATTENTION / CRITICAL
- **Scores**: architecture, code_quality, security, maintainability, test_coverage (each 0-10)
- **Findings** grouped by severity:
  - Critical findings (numbered, with location)
  - Major findings (numbered, with location)
  - Minor findings + suggestions (summarized)
- **Priority actions**: top recommended actions

### User Decision

Ask the user:
> "Which items would you like me to fix? You can:
> - List finding numbers (e.g., '1, 3, 5')
> - Say 'all critical' or 'all major'
> - Say 'none' to just keep the report"

If user selects items:
- Proceed to B2

If user says none:
- Run Wrap-up and archive the report

## B2: Execute Fixes

1. Write `.review/current_plan.md` based on selected findings:
   - For each selected finding, create a step with the GPT's suggestion as guidance
   - Keep the plan focused — only fix what was selected

2. Update state: `"state": "executing"`

3. **Check working tree** (same as A3 step 2)

4. Implement the fixes.

5. Write completion summary to `.review/completion_summary.md`:
   - List which health check findings were addressed
   - What was changed for each

6. Collect diff (same as A3 step 6).

7. Update state: `"state": "change_pending_review"`

8. Tell user: "Fixes complete. Submitting completion report to reviewer..."

## B3: Completion Review

Same as A4 — GPT reviews the implementation against the plan (which is based on the health check findings).

---

# Wrap-up (shared by both workflows)

Run context update:

```bash
python3 SKILL_DIR/scripts/update_context.py \
  --state-dir .review/ \
  --task-id <task_id>
```

This archives task artifacts to `history/`, updates `context_summary.md` and `open_issues.md`.

Update state: `"state": "idle", "task_id": null`

Present final summary to the user:
- Task completed
- Final verdict and scores
- Any open issues noted for future tasks

---

## Status Check (`/ai-reviewer status`)

Read `.review/review_state.json` and present:
- Current state (idle, plan_pending_review, executing, health_check, etc.)
- Current task ID and description
- Revision/fix counts
- Last verdict

Suggest the appropriate next action based on state.

---

## State Machine

```
                    ┌─────────────────────────────────────┐
                    │            Workflow A: Task           │
                    │                                       │
                    │  planning → plan_pending_review        │
                    │               │                        │
                    │               ├─ APPROVE → plan_approved
                    │               ├─ REVISE → ask user → plan_approved
                    │               └─ BLOCK → idle          │
                    │                          │             │
                    │              plan_approved             │
                    │               │ user confirms          │
                    │               ▼                        │
           idle ───►│          executing                    │
             ▲      │               │                        │
             │      │               ▼                        │
             │      │     change_pending_review              │
             │      │               │                        │
             │      │               ├─ APPROVE → completed   │
             │      │               ├─ REVISE → ask user → completed
             │      │               └─ BLOCK → user decides  │
             │      └───────────────┬───────────────────────┘
             │                      │
             │      ┌───────────────┼───────────────────────┐
             │      │               │ Workflow B: Check      │
             │      │               │                        │
             │      │       health_check                     │
             │      │               │                        │
             │      │       health_check_complete            │
             │      │               │                        │
             │      │    user picks fixes? ──no──→ completed │
             │      │               │yes                     │
             │      │          executing → change_pending... │
             │      │               (same as Workflow A)     │
             │      └───────────────┬───────────────────────┘
             │                      │
             │              completed                        
             │                      │ context update + archive
             └──────────────────────┘
```

REVISE always asks user first, then proceeds forward (no loop back to reviewer).

---

## Error Recovery

If a script fails (non-zero exit):
1. Show the error to the user
2. Do NOT change review_state.json
3. Suggest: "The reviewer encountered an error. You can retry or proceed manually."

If state is stuck (e.g., `executing` but user wants to restart):
- Offer to reset: update `review_state.json` to `idle`
- Archive current artifacts first

---

## Rules

1. **Never skip review gates** — plan review and completion review are mandatory
2. **Never auto-apply reviewer suggestions** — always ask user before making changes from a REVISE verdict
3. **Never auto-commit** — user manages their own git commits
4. **All .review/ artifacts in English** — translate only for user-facing messages
5. **Reviewer is read-only** — the reviewer script runs Codex with `--sandbox read-only`
6. **Max revisions are configurable** — read from `.review/config.json`, not hardcoded
7. **Archive before reset** — always run update_context.py before resetting to idle
8. **Show don't hide** — always show the user the full review results, scores, and findings
9. **No re-review after REVISE** — when user approves fixes from a REVISE verdict, apply them and move forward; do NOT re-submit to the GPT reviewer
10. **Completion summary is natural** — write it as you would normally summarize your work; no special format required
