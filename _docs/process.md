# Process Guidelines & Orchestration Graph

## Roles
- PM: Grooms a task before implementation (`_docs/team/pm.md`).
- Engineer: Implements one groomed task (`_docs/team/software-engineer.md`).
- QA: Checks work against acceptance criteria (`_docs/team/qa-engineer.md`).

Orchestrator

The main session is the orchestrator. It coordinates the lifecycle across the PM, Engineer, and QA roles. Where supported by the execution environment, subagents are launched for each role; in headless CLI environments where background subagent prompts are suppressed, the orchestrator executes each phase sequentially adhering strictly to the respective role definition contracts (`_docs/team/pm.md`, `_docs/team/software-engineer.md`, `_docs/team/qa-engineer.md`).

## Orchestrator Lifecycle
1. Select the next open issue from GitHub Issues.
2. PM grooms the issue into `_docs/task-template.md` format.
3. Software Engineer implements the task and writes unit tests.
4. QA Engineer verifies code against acceptance criteria.
   - On FAIL: Return to Step 3 with QA error log as input.
   - On PASS: Orchestrator closes the issue.
5. Repeat until backlog is complete.
