---
name: ponytail-review-code
description: Review IdeaHub code or diffs for real defects and needless complexity. Use for code review requests in this repository.
---

# Ponytail review for IdeaHub

Load and follow the `ponytail` skill at full intensity unless the user selected another level. Review the requested diff or files; if no scope is given, start with the current Git changes.

Trace each changed behavior through its relevant callers and layers: Flask route or controller, service, repository or model, and any Jinja or root `static/` client code involved. Check authorization, CSRF, input validation, money and stock transitions, database writes, and Socket.IO effects when the change touches them. Use the isolated tests in `tests/` only when a targeted check helps confirm a finding.

Report actionable findings in impact order. For each, give the exact file and line, a reproducible scenario or code path, the consequence, and the smallest correct fix. Identify removable duplication or an unnecessary dependency only when removal preserves behavior. Skip style-only comments and speculative abstractions. If no findings remain, say so and mention any meaningful unverified risk.

For a review-only request, report findings without editing. When the user asks to fix issues, make the smallest correct changes and verify the affected behavior.
