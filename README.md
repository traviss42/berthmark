# Berthmark

> **Maritime Port-Call Risk Intelligence & Operational Monitoring Platform**

Berthmark is an interactive platform that monitors, evaluates, and alerts maritime stakeholders about operational disruptions, berth bottlenecks, navigational constraints, and severe weather risks across key global ports.

Built to comply with international maritime guidelines (**PIANC Report 121**) and employing the **Maximum Severity ("Weakest-Link") Rule**, Berthmark translates complex oceanographic and vessel traffic telemetry into actionable risk intelligence for vessel operators, charterers, and port authorities.

---

## Table of Contents

- [Key Capabilities](#key-capabilities)
- [Architecture & Tech Stack](#architecture--tech-stack)
- [Real Data Sources & Multi-Tier Caching](#real-data-sources--multi-tier-caching)
- [Prerequisites](#prerequisites)
- [Quickstart: Installation & Running](#quickstart-installation--running)
- [Makefile Command Reference](#makefile-command-reference)
- [External APIs & Diagnostic Probe](#external-apis--diagnostic-probe)
- [Automated Testing](#automated-testing)
- [API Reference & Swagger Documentation](#api-reference--swagger-documentation)
- [Project Layout](#project-layout)
- [UN/LOCODE Data Management](#unlocode-data-management)
- [License](#license)

---

## Key Capabilities

- **User Authentication & Private Portfolios:**
  - Secure email-based login (e.g. `operations@pacific-shipping.com`, `captain@rotterdam-logistics.nl`, or any organization email).
  - Multi-tenant data isolation ensures each operator maintains their own private monitored portfolio and state history.

- **Automated Email Notification Routing & Per-Port Opt-Out:**
  - The login email automatically serves as the verified destination where critical port risk state alerts are dispatched.
  - Newly monitored ports are **opted in by default** to keep operators immediately informed of weather disruptions and berth bottlenecks.
  - Operators can freely **opt out of notifications on a per-port basis** at any time with a single click from the monitored list or port risk detail view.

- **User-Driven Port Portfolio:**
  - Users curate their own portfolio by searching over 100,000+ official ports from the global UN/LOCODE database.
  - Track any port with custom geofence radii.
  - Easily remove any port from monitoring with a single click directly from the list or detail view.

- **Vessel-Class Specific Risk Profiling:**
  - Evaluates operational limits tailored to 13 distinct vessel classes across 4 sectors:
    - **Containerized:** Feeder, Panamax / Sub-Panamax, Neo-Panamax, Ultra Large Container Vessel (ULCV).
    - **Liquid Bulk (Tankers):** MR / Handysize, Aframax, Suezmax, VLCC / ULCC.
    - **Dry Bulk:** Handysize / Supramax, Panamax (Bulk), Capesize.
    - **Specialized:** PCC / PCTC (Car Carriers), LNG / LPG Carriers.

- **Multi-Factor Risk Engine & Weakest-Link Rule:**
  - **Congestion Risk:** Active anchorage queues and waiting times evaluated against rolling 30-day baselines alongside berth occupancy percentages.
  - **Terminal Delays:** Turnaround times, berth-to-anchorage wait ratios, and dwell time anomalies.
  - **Marine Weather:** Real-time wind speed, peak gusts, significant wave height, swell period, and visibility.
  - **Navigational Safety:** Dynamic Under-Keel Clearance (UKC), channel navigation depth, air draft clearance under bridges, harbor pilot availability, and tidal elevation.
  - **Weakest-Link Composite Rule:** Any single sub-risk reaching **High** severity automatically elevates the port's composite status to **High**, preventing critical hazards from being masked by average scores.

- **State Transition Alerts & Notification Feed:**
  - Real-time in-app notification center that records risk state shifts (e.g., Low → Medium, Medium → High) with anti-flapping cooldown protection.
  - Displays destination email badges indicating exactly where alerts were dispatched.

---

## Architecture & Tech Stack

```text
┌─────────────────────────────────────────────────────────────┐
│                       React Frontend                        │
│          (TypeScript, Tailwind CSS, Vite, Lucide)           │
│                 http://localhost:5173                       │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / JSON
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Backend API                      │
│            (Python 3.11+, Pydantic v2, Uvicorn)             │
│                 http://localhost:8000                       │
└──────┬───────────────────────┬──────────────────────────────┘
       │                       │
       ▼                       ▼
┌──────────────┐    ┌────────────────────┐    ┌───────────────┐
│  SQLAlchemy  │    │    Open-Meteo      │    │   AISStream   │
│ Database URL │    │  Marine & Forecast │    │   WebSocket   │
│(SQLite / PG) │    │   (Live Weather)   │    │(Live AIS/MMSI)│
└──────────────┘    └────────────────────┘    └───────────────┘
```

- **Frontend:** React 18, TypeScript, Tailwind CSS, Vite, Lucide Icons, Vitest.
- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.0+, Pydantic v2, Uvicorn, httpx, websockets, pytest.
- **Database Layer:** Database-agnostic SQLAlchemy ORM with connection pooling. Driven by `DATABASE_URL` (SQLite file by default, ready for PostgreSQL, MySQL, etc.).
- **Version Management:**
  - Node managed via `fnm` (Fast Node Manager).
  - Python managed via `pyenv` with an isolated local virtual environment (`backend/.venv`).

---

## Real Data Sources & Multi-Tier Caching

Berthmark does not rely on mock databases; it connects directly to live maritime services:

1. **UN/LOCODE Maritime Database (SQLite):**
   - High-performance local SQLite database (`backend/data/unlocode.db`) seeded with UN/ECE standard location codes and parsed coordinates.
2. **Open-Meteo Marine & Atmospheric Weather API:**
   - Real-time wave height, wind speed, gust velocity, and swell period fetched directly from Open-Meteo endpoints.
3. **AISStream Live Vessel Traffic (WebSocket API):**
   - Direct WebSocket streaming (`wss://stream.aisstream.io/v0/stream`) sampling real-time AIS vessel position reports and ship static data within dynamic port geofence bounding boxes.

### Multi-Tier Caching System

To minimize network latency, avoid redundant round-trips, and respect third-party rate limits, Berthmark implements intelligent caching across every layer:

| Layer | Component | TTL | Strategy | Force Refresh |
| :--- | :--- | :--- | :--- | :--- |
| **Backend** | Marine Weather Client | 15 Minutes | In-memory key by `lat:lon` | Supported |
| **Backend** | AISStream Traffic Client | 5 Minutes | In-memory key by `port_id:vessel_class` | Supported |
| **Backend** | Risk Assessment Service | 5 Minutes | In-memory key by `port_id:vessel_class` | `forceRefresh=true` query param |
| **Backend** | Historical Trend Engine | 5 Minutes | In-memory key by `port_id:vessel_class:days` | `forceRefresh=true` query param |
| **Frontend** | Port Directory Search | 5 Minutes | Client-side memory cache by normalized query | Automatic cache invalidation |

*Note: Clicking the **Refresh** button in the UI automatically sends `forceRefresh=true`, bypassing server caches and pulling fresh readings directly from external APIs.*

---

## Prerequisites

Before starting, ensure your system has the following tools installed:

- **Git**
- **GNU Make** (`make`)
- **Python 3.11+** (managed via `pyenv` recommended)
- **Node.js 18+** (managed via `fnm` recommended)

---

## Quickstart: Installation & Running

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/berthmark.git
cd berthmark
```

### 2. Configure Environment Variables

Copy the example configuration to `backend/.env`:

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` to configure your settings.

```env
# Database Configuration (Database-Agnostic SQLAlchemy URL)
# SQLite (default):
DATABASE_URL=sqlite:///backend/data/berthmark.db
# PostgreSQL (example):
# DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/berthmark

# Live AISStream vessel tracking (Optional: free API key from aisstream.io)
AISSTREAM_API_KEY=your_aisstream_api_key_here
```

*(If `AISSTREAM_API_KEY` is left blank, the application will automatically fall back to deterministic vessel traffic models without crashing).*

### 3. One-Command Setup

Install all backend virtual environment dependencies, initialize the UN/LOCODE SQLite database, and install frontend packages with:

```bash
make install
```

### 4. Start the Application

Launch both the FastAPI backend and React frontend concurrently:

```bash
make dev
```

Once started:
- **Web Application:** Open [http://localhost:5173](http://localhost:5173) in your browser.
- **FastAPI Interactive API Docs:** Visit [http://localhost:8000/docs](http://localhost:8000/docs).

*Press `Ctrl+C` in your terminal to cleanly stop both servers.*

---

## Makefile Command Reference

A comprehensive `Makefile` is provided to streamline development, testing, and lifecycle management:

| Command | Description |
| :--- | :--- |
| `make install` | Full installation: sets up Python `.venv`, installs pip packages, seeds SQLite DB, and runs `npm install`. |
| `make dev` | Launches both backend (:8000) and frontend (:5173) concurrently with unified logging and graceful shutdown. |
| `make run-backend` | Starts only the FastAPI backend server on [http://localhost:8000](http://localhost:8000). |
| `make run-frontend` | Starts only the Vite React frontend server on [http://localhost:5173](http://localhost:5173). |
| `make test` | Runs the full verification suite (both backend pytest and frontend vitest). |
| `make test-backend` | Runs the backend unit and integration tests with pytest. |
| `make test-frontend` | Runs the frontend test suite with vitest. |
| `make test-apis` | Runs the live external API diagnostic probe (Open-Meteo, AISStream, UN/LOCODE SQLite). |
| `make build` | Builds the production-ready frontend bundle into `frontend/dist`. |
| `make seed-db` | Seeds or re-indexes `backend/data/unlocode.db` from `backend/data/maritime_ports.json`. |
| `make clean` | Removes `__pycache__`, `.pytest_cache`, and frontend build artifacts. |

---

## External APIs & Diagnostic Probe

You can test live connectivity and authentication with all external APIs at any time by running:

```bash
make test-apis
```

This runs `backend/scripts/test_apis.py`, which performs live diagnostics against:
1. **UN/LOCODE SQLite DB:** Checks database integrity, record count, and sample coordinate queries.
2. **Open-Meteo API:** Sends a live test request to verify oceanographic and atmospheric wind/gust telemetry.
3. **AISStream WebSocket:** Opens a live WebSocket handshake with `wss://stream.aisstream.io/v0/stream`, authenticates your `AISSTREAM_API_KEY`, verifies subscription confirmation, and counts real-time active vessels.

Sample diagnostic output:
```text
====================================================
    Berthmark - External APIs Diagnostic Suite     
====================================================

1. UN/LOCODE Maritime Database (SQLite)
   --------------------------------------
   ✔ CONNECTED & HEALTHY (77.0 ms)
     • Total indexed ports: 44
     • Sample lookup ('Rotterdam'): Port of Rotterdam [NLRTM]

2. Marine & Atmospheric Weather API (Open-Meteo)
   ---------------------------------------------
   ✔ CONNECTED & HEALTHY (1037.6 ms)
     • Endpoint: https://api.open-meteo.com/v1/forecast
     • Live wind at Port of Rotterdam: 6.2 knots (gusts: 14.2 knots)

3. AISStream Live Vessel Traffic (WebSocket API)
   ---------------------------------------------
     • API Key loaded: d7854e...c07c (length: 40)
   ✔ AUTHENTICATED & STREAMING (4796.4 ms)
     • Endpoint: wss://stream.aisstream.io/v0/stream
     • Subscription confirmation: Accepted
     • Real-time vessels sampled in Rotterdam geofence: 21

Summary:
  • UN/LOCODE Database:  [PASS]
  • Open-Meteo Weather:  [PASS]
  • AISStream WebSocket: [PASS]

All external APIs and datasets are online, authenticated, and functioning properly!
```

---

## Automated Testing

Berthmark includes full test suites covering business logic, weakest-link scoring rules, API endpoints, caching behavior, and frontend components:

```bash
# Run all tests (backend + frontend)
make test

# Or run separately
make test-backend    # 37 passed
make test-frontend   # 39 passed
```

---

## API Reference & Swagger Documentation

When the backend is running (`make run-backend` or `make dev`), visit [http://localhost:8000/docs](http://localhost:8000/docs) for the interactive OpenAPI/Swagger explorer, or [http://localhost:8000/redoc](http://localhost:8000/redoc) for ReDoc.

### Core Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/auth/login` | Authenticate with email (sets destination for email alerts). |
| `GET` | `/api/v1/auth/me` | Fetch currently authenticated user session. |
| `POST` | `/api/v1/auth/logout` | Revoke user authentication session. |
| `GET` | `/api/v1/ports` | List ports monitored by the authenticated user. |
| `POST` | `/api/v1/ports` | Add a port to the user's private monitored portfolio (default: notifications enabled). |
| `DELETE` | `/api/v1/ports/{portId}` | Remove a port from the user's monitored portfolio. |
| `PATCH` | `/api/v1/ports/{portId}/notifications` | Toggle email alert notifications on/off for a specific port. |
| `GET` | `/api/v1/ports/search?q={query}` | Search the global UN/LOCODE database by name, code, or country. |
| `GET` | `/api/v1/ports/defaults` | Reference list of standard global maritime hubs. |
| `GET` | `/api/v1/ports/{portId}` | Get details of a specific port. |
| `GET` | `/api/v1/ports/{portId}/risk` | Compute real-time risk assessment for a port and vessel class (`forceRefresh=true` optional). |
| `POST` | `/api/v1/risk/bulk-assessments` | Bulk evaluate risk assessments across multiple ports. |
| `GET` | `/api/v1/ports/{portId}/risk/trend` | Retrieve chronological 6-hour evaluation cycles for historical trend charts. |
| `GET` | `/api/v1/notifications` | Get state-change risk alert notifications (includes destination email). |
| `PATCH`| `/api/v1/notifications/{id}/read`| Mark a specific notification as read. |
| `POST` | `/api/v1/notifications/mark-all-read` | Mark all user notifications as read. |
| `GET` | `/health` | System health check and status. |

---

## Project Layout

```text
berthmark/
├── backend/
│   ├── app/
│   │   ├── auth/             # Bearer authentication & user isolation dependencies
│   │   ├── clients/          # External API clients (AISStream WS, Open-Meteo, UN/LOCODE SQLite)
│   │   ├── db/               # SQLAlchemy database layer (Base, models, session, engine)
│   │   ├── models/           # Pydantic v2 schemas (Port, RiskAssessment, Notifications, Auth)
│   │   ├── routers/          # FastAPI REST endpoints (/ports, /risk, /notifications, /auth)
│   │   ├── services/         # Risk computation engine, weakest-link evaluator, port service, email service
│   │   ├── config.py         # Application settings via pydantic-settings (DATABASE_URL, etc.)
│   │   └── main.py           # FastAPI application entrypoint, lifespan DB init, and middleware
│   ├── data/
│   │   ├── maritime_ports.json  # Seed dataset of major global maritime hubs
│   │   ├── unlocode.db          # Embedded SQLite database of UN/LOCODE locations
│   │   └── berthmark.db         # Default SQLite operational database (monitored ports, notifications)
│   ├── scripts/
│   │   ├── import_unlocode.py   # CLI tool to seed and import full UNECE CSV releases
│   │   └── test_apis.py         # Standalone external API connectivity probe
│   ├── tests/                   # Pytest test suite (test_database, test_auth, test_ports, etc.)
│   │   ├── test_database.py     # Database engine, URL resolution, and SQLAlchemy CRUD tests
│   │   ├── test_auth.py         # Login, logout, profile, and authorization tests
│   │   ├── test_ports.py        # Port management, search, and notification opt-in/opt-out
│   │   └── ...
│   ├── .env.example             # Template for backend environment variables
│   └── requirements.txt         # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── components/       # UI components (LoginScreen, PortList, PortSearch, PortRiskDetail)
│   │   ├── context/          # React AuthContext providing login state and user session
│   │   ├── hooks/            # Custom React hooks (usePorts, useRiskAssessments, useNotifications)
│   │   ├── services/         # API HTTP client (ApiPortService, ApiRiskService, ApiAuthService)
│   │   ├── types/            # TypeScript interfaces, User models, and vessel taxonomy
│   │   ├── utils/            # Risk color palettes, tier formatting, math helpers
│   │   ├── App.tsx           # Dashboard layout, state orchestration, refresh handling

│   │   └── main.tsx          # React application entrypoint
│   ├── package.json          # Node dependencies and scripts
│   ├── tsconfig.json         # TypeScript compiler configuration
│   └── vite.config.ts        # Vite configuration and proxy rules
├── docs/                     # Specifications and architectural design documents
├── Makefile                  # Lifecycle automation commands
└── README.md                 # Project documentation
```

---

## UN/LOCODE Data Management

UN/ECE distributes the UN/LOCODE database biannually as flat files. Berthmark includes an embedded SQLite database engine with an automated CLI importer:

- **Automatic Seeding:** Running `make install` automatically creates and indexes `backend/data/unlocode.db` from `backend/data/maritime_ports.json`.
- **Importing Official UNECE Releases:** If you obtain the full UNECE CSV releases (~110,000 global locations), you can import them directly:
  ```bash
  # Import a single UNECE CSV file:
  python backend/scripts/import_unlocode.py --csv path/to/2024-1_CodeList.csv

  # Import directory of UNECE part files:
  python backend/scripts/import_unlocode.py --dir path/to/csv_parts/
  ```
  The importer filters for maritime/waterborne facilities (`Function` code 1) and converts coordinate notations (`DDMM[N/S] DDDMM[E/W]`) to decimal degrees.

---

## License

This project is licensed under the MIT License.
