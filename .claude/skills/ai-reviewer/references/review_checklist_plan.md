# Plan Review Checklist

Evaluate the plan against each item. For each, note: pass / concern / fail.

## Requirements Coverage
- [ ] Every stated requirement has at least one plan step addressing it
- [ ] No requirements are misinterpreted or only partially covered
- [ ] Success criteria in the feature contract are achievable via the planned steps

## Assumptions
- [ ] The plan does not assume files, functions, or APIs exist without verification
- [ ] Technology choices match what the project already uses
- [ ] No incorrect assumptions about the project's architecture or patterns

## Scope
- [ ] The plan does not include unnecessary refactoring or "improvements"
- [ ] No speculative features or "while we're at it" additions
- [ ] File scope is minimal — only files that need changing are listed

## Specificity
- [ ] Each step is concrete enough that a developer could execute it without guessing
- [ ] File paths and function names are specified where relevant
- [ ] No vague steps like "refactor as needed" or "clean up"

## Risks
- [ ] Potential failure points are identified
- [ ] Edge cases are considered
- [ ] Impact on existing functionality is assessed

## Test Strategy
- [ ] The plan includes how to verify the changes work
- [ ] Test approach matches the project's existing test patterns
- [ ] Acceptance criteria are testable
