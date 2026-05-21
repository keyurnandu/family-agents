## Skill: Uishiftbackend-learning

- **Recognize backend-UI integration friction**: Watch for issues where UI changes require backend refactoring—especially around state synchronization, API contracts, or data shape mismatches. These are high-leverage problems to solve systematically.

- **Document the root cause, not just the fix**: When resolving UIShift backend issues, capture *why* the problem occurred (e.g., unclear API boundaries, missing versioning, tight coupling) alongside the solution. This pattern detection prevents recurrence.

- **Apply separation of concerns**: Use insights from this issue to enforce clear contracts between frontend and backend layers in new projects—define schemas early, version APIs explicitly, and avoid UI-driven database changes.

- **Extract reusable patterns into templates**: If the issue revealed a common pattern (e.g., state reconciliation, API migration strategies, backend layer abstraction), codify it as a reference architecture, example, or checklist for future projects.

- **Reference this in code reviews**: When reviewing similar backend-UI changes, cite the learnings from this issue to catch problems early—ask reviewers: "Does this risk the same coupling issues we hit before?"

- **Update team documentation**: Share key insights in your team's internal wiki, decision records, or architecture guidelines so learnings compound across projects and new team members benefit.