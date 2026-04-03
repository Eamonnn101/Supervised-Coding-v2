# Project Health Check Checklist

Perform a comprehensive audit of the project. Read the source files and evaluate each area below.

## Architecture
- [ ] Clear separation of concerns between modules
- [ ] No circular dependencies
- [ ] Consistent patterns across similar components
- [ ] Appropriate level of abstraction (not over-engineered, not under-structured)

## Code Quality
- [ ] Consistent naming conventions
- [ ] No dead code or unused imports
- [ ] Error handling is present and appropriate
- [ ] No hardcoded values that should be configurable

## Security
- [ ] No command injection risks in subprocess calls
- [ ] Path handling is safe (no traversal vulnerabilities)
- [ ] No secrets or credentials in source code
- [ ] Input validation at system boundaries

## Maintainability
- [ ] Code is readable without excessive comments
- [ ] Functions/methods have clear, single responsibilities
- [ ] Configuration is externalized where appropriate
- [ ] Dependencies are reasonable and up-to-date

## Performance
- [ ] No obvious O(n^2) or worse algorithms on large inputs
- [ ] File I/O is bounded (no unbounded reads)
- [ ] No resource leaks (unclosed files, connections)

## Testing
- [ ] Test coverage exists for critical paths
- [ ] Tests are meaningful (not just trivial assertions)
- [ ] Test setup/teardown is clean
- [ ] Edge cases are covered

## Instructions

- Read the project files systematically — start from entry points, follow the call graph
- Use the project brief for orientation but verify everything by reading the actual code
- Cite specific file:line locations for all findings
- Severity guide:
  - **critical**: Security vulnerability, data loss risk, or crash in normal operation
  - **major**: Bug, logic error, or significant maintainability problem
  - **minor**: Style issue, minor inefficiency, or small improvement opportunity
  - **suggestion**: Nice-to-have improvement, not a problem per se
