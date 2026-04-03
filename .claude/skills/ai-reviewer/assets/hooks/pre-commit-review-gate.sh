#!/bin/bash
# Pre-commit hook: blocks commits when a review cycle is active but not yet approved.
# Installed by ai-reviewer init. User can bypass with: git commit --no-verify

STATE_FILE=".review/review_state.json"

# No .review/ directory = no enforcement
if [ ! -f "$STATE_FILE" ]; then
    exit 0
fi

# Read current state
STATE=$(python3 -c "
import json, sys
try:
    data = json.load(open('$STATE_FILE'))
    print(data.get('state', 'idle'))
except Exception:
    print('idle')
" 2>/dev/null)

case "$STATE" in
    idle|completed|plan_approved|executing)
        exit 0
        ;;
    plan_pending_review|change_pending_review)
        echo ""
        echo "  BLOCKED: Review pending (state: $STATE)"
        echo "  Complete the review cycle before committing."
        echo "  To bypass: git commit --no-verify"
        echo ""
        exit 1
        ;;
    *)
        exit 0
        ;;
esac
