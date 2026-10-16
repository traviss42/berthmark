# Berthmark

> Port-Call Risk Tracking & Assessment Tool

Berthmark is an interactive application designed to monitor, analyze, and alert maritime stakeholders about operational disruptions, bottlenecks, and safety risks across key global ports.

---

## Features

- **Multi-Category Risk Assessment:** Evaluates risk across four key operational dimensions:
  - **Congestion Risk:** Active anchorage queue counts and waiting times relative to rolling historical baselines.
  - **Terminal Delays:** Turnaround and dwell time anomaly tracking.
  - **Weather Delays:** Real-time wind speed, wave height, swell period, and visibility metrics.
  - **Navigational Risk:** Environmental constraints compared against channel, draft, and pilotage limits (PIANC Guidelines).
- **Vessel-Class Specific Profiling:** Differentiates risk based on global vessel taxonomy (Containerships, Tankers, Dry Bulk, Gas Carriers, Car Carriers).
- **Maximum Severity ("Weakest-Link") Rule:** Highlights immediate operational vulnerabilities if any single sub-category breaches critical safety thresholds.
- **Dynamic Baselines & Hard Safety Standards:** Blends rolling 30-day statistical anomaly detection with hard operational safety floors.
- **Multi-Tenant Private Tracking:** Allows users to track default global ports or add custom, private ports using UN/LOCODE.
- **Alerts & Notifications:** In-app risk badges and updates with anti-flapping cooldown logic.

---

## Project Structure

```text
├── frontend/          # React + TypeScript web application (Tailwind CSS, Vite)
├── backend/           # Python API backend (FastAPI / service layer)
├── docs/              # Specifications, architecture, and feature roadmaps
└── AGENTS.md          # Tech stack rules and developer workflow guide
```

---

## Tech Stack

- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS, Lucide Icons, Vitest
- **Backend:** Python (pyenv + `.venv`)
- **Node Management:** `fnm` (Fast Node Manager)

---

## Getting Started

### Prerequisites

- Node.js (managed via `fnm`)
- Python 3.11+ (managed via `pyenv`)

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

To run frontend tests:

```bash
npm run test # or npx vitest run
```

---

## Documentation

See [`docs/plan.md`](docs/plan.md) for the detailed MVP architecture, scoring logic, and data ingestion model.
