# AGENTS.md

## Commands
- `uv sync` - Install and synchronize backend Python dependencies
- `uv run pytest` - Run backend Pytest unit and integration tests
- `npm --prefix frontend install` - Install frontend Node dependencies
- `npm --prefix frontend run dev` - Launch Vite React development server

## Rules
- Dependencies belong in `pyproject.toml` (backend) and `package.json` (frontend). Do not add dependencies without asking.
- Do not modify API endpoint structures without updating `openapi.yaml`.
- Never hardcode data, coordinates, or domain lookup tables in application code. All operational and geospatial data must be resolved dynamically via database queries, schemas, or API contracts.
- Commit code regularly to Git after completing logical sub-tasks.

## Documents
- `_docs/process.md` - How work is organized (PM grooming, SWE implementation, QA verification, and orchestrator graph)
- `_docs/task-template.md` - Template schema for groomed backlog tasks
- `_docs/team/pm.md` - Product Manager subagent role definition
- `_docs/team/software-engineer.md` - Software Engineer subagent role definition
- `_docs/team/qa-engineer.md` - QA Engineer subagent role definition
- `openapi.yaml` - Shared API contract between React frontend and FastAPI backend
