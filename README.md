# Supervised Coding v2

Dual-agent supervised coding system: **Claude Code writes, GPT reviews**.

Claude Code acts as the writer and orchestrator. GPT (via [Codex CLI](https://github.com/openai/codex)) serves as an independent, read-only reviewer that evaluates plans and code changes with structured scoring.

## How It Works

```
┌─────────────┐     writes code      ┌─────────────┐
│  Claude Code │ ──────────────────── │   Project    │
│  (Writer)    │                      │   Files      │
└──────┬───────┘                      └──────────────┘
       │ invokes                             ▲
       ▼                                     │ reads (sandbox)
┌─────────────┐                              │
│  Codex CLI   │ ─────────────────────────────┘
│  GPT-5.4     │  returns structured JSON verdict
│  (Reviewer)  │  APPROVE / REVISE / BLOCK
└─────────────┘
```

## Three Core Functions

### 1. Task Workflow (`/ai-reviewer <task>`)

For new features or changes. Claude generates a plan, GPT reviews it, Claude implements, GPT verifies completion.

```
User describes task
  → Claude writes plan
  → GPT reviews plan (APPROVE / REVISE / BLOCK)
  → Claude implements code
  → GPT reviews completion against plan
  → Done
```

### 2. Health Check (`/ai-reviewer check`)

For existing projects. GPT audits the entire codebase and produces a findings report with severity levels.

```
User requests check
  → GPT reads project files, evaluates 6 dimensions
  → Returns findings (critical / major / minor / suggestion)
  → User picks which to fix
  → Claude implements fixes
  → GPT reviews completion
  → Done
```

### 3. Status (`/ai-reviewer status`)

Shows current workflow state, pending actions, and review history.

## Scoring Dimensions

**Task & Completion Review**: alignment, correctness, maintainability, simplicity, test_readiness (0-10 each)

**Health Check**: architecture, code_quality, security, maintainability, test_coverage (0-10 each)

## Project Structure

```
.claude/skills/ai-reviewer/
├── SKILL.md                              # Orchestration — workflow definitions
├── scripts/
│   ├── reviewer.py                       # Codex CLI invocation + context assembly
│   ├── init_project.py                   # Project scan + .review/ bootstrap
│   └── update_context.py                 # Context accumulation + archival
├── references/
│   ├── reviewer_identity.md              # Reviewer persona (Staff Engineer)
│   ├── review_checklist_plan.md          # Plan review checklist
│   ├── review_checklist_change.md        # Change review checklist
│   └── review_checklist_health.md        # Health check checklist
└── assets/
    ├── plan_review_schema.json           # JSON Schema — plan review output
    ├── change_review_schema.json         # JSON Schema — change review output
    ├── health_check_schema.json          # JSON Schema — health check output
    └── hooks/
        └── pre-commit-review-gate.sh     # Git hook — blocks commits during pending reviews
```

## Key Design Decisions

- **Claude writes, GPT reviews** — independent evaluation catches self-review blind spots
- **Structured JSON output** — every review returns machine-parseable scores and findings
- **Continuous context** — reviewer accumulates patterns across reviews via `context_summary.md`
- **User in control** — REVISE suggestions require user approval before changes are applied; no auto-apply, no auto-commit
- **No re-review loops** — after user approves fixes, proceed forward; don't re-submit to GPT
- **Read-only reviewer** — Codex runs with `--sandbox read-only`, can never modify project files
- **All internal artifacts in English** — user-facing output follows the user's language

## Setup

### Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed
- [Codex CLI](https://github.com/openai/codex) installed and authenticated (`codex` on PATH)
- Python 3.9+
- Git

### Install

Clone and register as a Claude Code skill:

```bash
git clone https://github.com/Eamonnn101/Supervised-Coding-v2.git
```

Then in your target project, initialize the reviewer:

```
/ai-reviewer init
```

This creates a `.review/` directory in your project with configuration and state files.

### Configuration

Edit `.review/config.json` in your target project:

```json
{
  "reviewer_cli": "codex",
  "reviewer_model": "gpt-5.4",
  "timeout_seconds": 600,
  "max_context_chars": 100000,
  "max_plan_revisions": 3,
  "max_fix_cycles": 3,
  "validation_commands": [],
  "language": "auto"
}
```

## State Files (`.review/`)

Created per-project by `/ai-reviewer init`. Not committed to git.

| File | Purpose |
|------|---------|
| `config.json` | Reviewer settings |
| `project_brief.md` | Auto-generated project overview |
| `review_state.json` | Workflow state machine |
| `review_log.jsonl` | Append-only review history |
| `context_summary.md` | Accumulated reviewer context |
| `open_issues.md` | Unresolved issues from past reviews |
| `history/` | Archived task artifacts |

## v1 → v2

| | v1 | v2 |
|---|---|---|
| Writer | Codex CLI | Claude Code |
| Reviewer | Claude CLI | Codex CLI (GPT) |
| Reviewer memory | None | Continuous context |
| Enforcement | Trust only | Git hooks + state machine |
| Health check | No | Yes |
| User control | Auto-apply | Ask before every change |
| Python infra | 15 modules | 3 scripts |

## License

MIT
