# AI Reviews AI Code v2

Dual-agent supervised coding: Claude (you) writes code, GPT reviews via Codex CLI.

## Usage

```
/ai-reviewer init              Initialize .review/ for a project
/ai-reviewer <task>            Plan → GPT review → Execute → GPT completion review
/ai-reviewer check             GPT project health check → User picks fixes → Execute
/ai-reviewer status            Check workflow state
```

## Architecture

- **Writer**: You (Claude Code) — write plans, implement code, orchestrate workflow
- **Reviewer**: GPT via Codex CLI (`codex exec --sandbox read-only`) — independent, read-only review
- **State**: `.review/` directory in the target project
- **Enforcement**: Git pre-commit hook blocks commits during pending reviews

## Key Rules

- All `.review/` artifacts are **English-only**
- User-facing output follows the user's language
- Never bypass review gates
- Never auto-commit or auto-approve
- Scripts are in `.claude/skills/ai-reviewer/scripts/`

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/reviewer.py` | Invoke Codex CLI for plan/change/health-check review |
| `scripts/init_project.py` | Scan project and create .review/ |
| `scripts/update_context.py` | Update context after task completion |

## Dependencies

- Codex CLI (`codex`) on PATH
- Python 3.9+
- Git in target project
