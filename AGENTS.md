## Tech Stack & Environment Constraints

### Frontend
- **Framework:** React with TypeScript
- **Node Version Management:** `fnm` (Fast Node Manager)
- **Rules:** Always use the active Node version managed by `fnm`. Do not attempt to install global npm packages without checking the environment.

### Backend
- **Language:** Python
- **Environment Management:** `pyenv`
- **Rules:** Use `pyenv` to manage and lock the Python version. Use a local virtual environment (`.venv`) within the backend directory for dependencies. Do not install packages globally.

## Workflow & Safety Guardrails
1. **Environment Awareness:** Before running terminal commands to install packages or start servers, ensure you are using `fnm` for frontend commands and the active `pyenv` virtual environment for backend commands.
2. **Incremental Changes:** Implement features in small, testable increments. Do not overwrite large files entirely if only minor edits are needed.

## Project Structure
Ensure the project follows this layout:
├── frontend/          # React + TypeScript web app (managed via fnm)
├── backend/           # Python API backend (managed via pyenv + .venv)
├── spec/              # Application specifications and feature docs
└── AGENTS.md          # This instruction file
