# AGENTS.md — Definitive Developer & Agent Onboarding Guide

> **Berthmark: Maritime Port-Call Risk Intelligence & Operational Monitoring Platform**  
> This document is the definitive engineering guide and system specification for any AI agent or software engineer working on Berthmark. It codifies the platform's architectural philosophy, technology stack, data pipelines, background streaming subsystems, development workflows, and non-negotiable safety guardrails.

---

## 1. Executive Summary & Domain Context

Berthmark is a real-time maritime port-call risk intelligence and operational monitoring system. Designed for ship operators, charterers, fleet managers, and port authorities, it continuously monitors navigational constraints, berth queues, and oceanographic/atmospheric hazards across global commercial ports.

### Core Domain Rules
1. **PIANC Report 121 Compliance:** Navigational safety metrics (under-keel clearance, channel depth, cargo pier depth, turning basins) are evaluated against design drafts of 13 specific vessel classes based on World Association for Waterborne Transport Infrastructure (PIANC) standards.
2. **Maximum Severity ("Weakest-Link") Principle:** Port risk is assessed across three discrete categories: **Navigational**, **Congestion**, and **Weather**. If any single category reaches **High Risk**, the composite risk of the port call is **High Risk**. Critical operational hazards must never be masked or diluted by averaging scores.
3. **Zero Simulated/Mock Data:** Synthetic fallbacks, randomized generators, and mocked telemetry are strictly forbidden in production code paths. Every single metric must originate from authenticated external sources (Open-Meteo API, AISStream.io WebSockets, and official NGA Pub 150 / UN/LOCODE hydrographic datasets).
4. **Empty User Portfolio Policy:** Berthmark does not force "starter hubs" or "special default ports" into any user's dashboard. A newly authenticated user starts with a completely empty portfolio (`0` ports). Operators explicitly search and add only the ports they wish to monitor.

---

## 2. System Architecture & Component Decoupling

Berthmark is strictly decoupled into a React Single Page Application (SPA) frontend and a Python FastAPI backend REST API. Communication occurs exclusively over standardized HTTP/JSON endpoints.

```text
┌────────────────────────────────────────────────────────────────────────┐
│                   React + TypeScript Web Client                        │
│                (Vite, Tailwind CSS, Lucide Icons)                      │
│                      http://localhost:5173                             │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP REST / JSON
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        FastAPI Backend API                             │
│               (Python 3.12, SQLAlchemy 2.0, Pydantic v2)               │
│                      http://localhost:8000                             │
└───────┬───────────────────────────┬────────────────────────────┬───────┘
        │                           │                            │
        ▼                           ▼                            ▼
┌──────────────────┐    ┌───────────────────────┐    ┌───────────────────┐
│ SQLite Databases │    │ Open-Meteo Weather    │    │ AISStream Workers │
│  • unlocode.db   │    │  • Marine API (Waves) │    │  • 3 Connections  │
│  • berthmark.db  │    │  • Forecast (Wind/Vis)│    │  • 2,477 Geofences│
└──────────────────┘    └───────────────────────┘    └───────────────────┘
```

### Directory Layout
```text
berthmark/
├── AGENTS.md                  # This definitive developer & agent onboarding guide
├── Makefile                   # Canonical workflow automation commands
├── README.md                  # User-facing platform documentation
├── openapi.yaml               # Formal OpenAPI 3.1 REST API specification
├── backend/                   # Python FastAPI application
│   ├── app/
│   │   ├── auth/              # JWT / token auth dependencies and handlers
│   │   ├── clients/           # External API & database clients
│   │   │   ├── ais_client.py          # On-demand AIS & NGA WPI metric builder
│   │   │   ├── ais_stream_manager.py  # 3-worker persistent AIS WebSocket manager
│   │   │   ├── ports_client.py        # Port directory client wrapper
│   │   │   ├── unlocode_db.py         # Read-only UN/LOCODE SQLite interface
│   │   │   └── weather_client.py      # Open-Meteo Marine & Atmospheric client
│   │   ├── db/                # SQLAlchemy session, engine, base, and models
│   │   ├── models/            # Pydantic schemas (requests, responses, domain)
│   │   ├── routers/           # FastAPI routers (auth, ports, risk, notifications)
│   │   ├── services/          # Core domain services
│   │   │   ├── email_service.py       # SMTP & console alert dispatching
│   │   │   ├── ingestion.py           # Background APScheduler & warm-up jobs
│   │   │   ├── notification_service.py# Rate-limited state alert service
│   │   │   ├── port_service.py        # Multi-tenant port portfolio manager
│   │   │   └── risk_service.py        # Composite & category risk engine
│   │   ├── config.py          # Centralized Pydantic application settings
│   │   └── main.py            # FastAPI entry point, lifespan, and CORS middleware
│   ├── data/
│   │   ├── unlocode.db        # Static reference DB (2,477 maritime ports)
│   │   └── berthmark.db       # Dynamic user DB & telemetry cache (auto-generated)
│   ├── scripts/               # Administrative & data import CLI scripts
│   └── tests/                 # Full pytest suite (61 unit & integration tests)
├── frontend/                  # React + TypeScript frontend
│   ├── src/
│   │   ├── components/        # UI components (PortList, PortSearch, RiskDetail, etc.)
│   │   ├── context/           # React context providers (AuthContext)
│   │   ├── data/              # Static vessel taxonomy definitions
│   │   ├── hooks/             # Custom hooks (usePorts, useRiskAssessments, useStreamStatus)
│   │   ├── services/          # HTTP service wrappers and frontend risk calculations
│   │   ├── types/             # TypeScript interfaces and domain types
│   │   ├── App.tsx            # Root application, login gate & warmup spinner
│   │   └── main.tsx           # React DOM bootstrap
│   └── package.json           # Frontend dependencies and scripts
└── docs/                      # Supplementary design specifications
```

---

## 3. Tech Stack & Environment Constraints

Strict versioning and environment isolation rules apply across all machines and agents:

### Frontend
- **Framework:** React 18 with TypeScript 5
- **Build Tool:** Vite 5
- **Styling:** Tailwind CSS with Lucide React icons
- **Test Runner:** Vitest
- **Node Version Management:** `fnm` (Fast Node Manager)
- **Constraint:** Always run frontend tools and scripts under the active Node version managed by `fnm` (e.g., `fnm exec --using=default npm ...`). Never install global npm packages.

### Backend
- **Language:** Python 3.12 (managed via `pyenv`)
- **Web Framework:** FastAPI 0.115+ with Starlette & Uvicorn
- **ORM / Database:** SQLAlchemy 2.0+ (database-agnostic, SQLite default)
- **Async & Scheduling:** `asyncio`, `websockets` 14+, APScheduler 3.10+
- **HTTP Client:** `httpx`
- **Validation:** Pydantic v2
- **Test Runner:** `pytest` with `pytest-asyncio`
- **Constraint:** Always use the dedicated virtual environment located at `backend/.venv`. Never install packages globally or modify system Python.

---

## 4. Databases & Storage Architecture

Berthmark separates read-only maritime reference data from mutable user portfolios and telemetry caches:

### 1. UN/LOCODE & NGA World Port Index Database (`backend/data/unlocode.db`)
- **Nature:** Static, read-only maritime reference database.
- **Port Population:** Exactly **2,477** global commercial sea ports.
- **Filtering Standard:** Intersection of UNECE UN/LOCODE (`Function = 1` *Maritime transport*) and NGA World Port Index (Pub 150 `UpdatedPub150.csv`) retaining ports with:
  1. Verified channel depth (`channel_depth_m > 0`).
  2. Valid geographic coordinates (`-90 <= lat <= 90`, `-180 <= lon <= 180`).
- **Hydrographic Fields:** Channel depth, cargo pier depth, anchorage depth, oil terminal depth, LNG terminal depth, maximum vessel draft, tidal range, overhead limits, pilotage availability, tug assistance, harbor size, and shelter afforded.

### 2. Application Database (`backend/data/berthmark.db`)
- **Nature:** Dynamic, read-write multi-tenant SQLite database (configurable to PostgreSQL via `DATABASE_URL`).
- **Tables:**
  - `monitored_ports`: User-monitored port subscriptions (`id`, `user_id`, `locode`, `name`, `lat`, `lon`, `geofence_radius_nm`, `vessel_class`, `notifications_enabled`, `created_at`). Scoped strictly by `user_id`.
  - `notification_records`: Persisted risk state transition logs and alert records (`id`, `user_id`, `port_id`, `category`, `old_tier`, `new_tier`, `detail`, `dispatched_to_email`, `created_at`).
  - `external_weather_cache`: Persisted marine and forecast weather telemetry (`wind_speed_knots`, `gust_speed_knots`, `wave_height_m`, `swell_period_sec`, `visibility_nm`, `fetched_at`).
  - `external_ais_traffic_cache`: Persisted vessel counts and navigational snapshots (`anchorage_queue_count`, `active_vessel_count`, `moving_vessel_count`, `rolling_30d_avg_queue`, `under_keel_clearance_m`, `channel_depth_m`, `fetched_at`).
- **Clean Slate Operation:** Run `make reset-db` to delete `berthmark.db` and start fresh. `unlocode.db` is strictly preserved.

---

## 5. Background Ingestion & AISStream Architecture

Live vessel tracking across thousands of global ports requires a resilient, non-blocking telemetry subsystem:

```text
 ┌────────────────────────────────────────────────────────┐
 │          All 2,477 Global Commercial Ports             │
 │          (from unlocode_ports in unlocode.db)          │
 └───────────────────────────┬────────────────────────────┘
                             │ Partition into 3 Slices (826, 826, 825)
                             ▼
  ┌─────────────────┬─────────────────┬─────────────────┐
  │ Worker 1/3 (0s) │ Worker 2/3(1.5s)│ Worker 3/3(3.0s)│
  │ ~826 Geofences  │ ~826 Geofences  │ ~825 Geofences  │
  └────────┬────────┴────────┬────────┴────────┬────────┘
           │ WebSocket       │ WebSocket       │ WebSocket
           ▼                 ▼                 ▼
  ┌─────────────────────────────────────────────────────┐
  │           wss://stream.aisstream.io/v0/stream       │
  └──────────────────────────┬──────────────────────────┘
                             │ Continuous PositionReport Packets
                             ▼
  ┌─────────────────────────────────────────────────────┐
  │      Shared In-Memory Registry (self._vessels)      │
  │      • Instant O(1) Queue Lookups                   │
  │      • 30-Minute Inactivity Vessel Pruning          │
  └──────────────────────────┬──────────────────────────┘
                             │ 20s Warm-Up Snapshot Flush (seen_port_ids = set())
                             ▼
  ┌─────────────────────────────────────────────────────┐
  │       SQLite Table: external_ais_traffic_cache      │
  └─────────────────────────────────────────────────────┘
```

### 1. 3 Concurrent WebSocket Connections
- **Account Limit Compliance:** AISStream accounts allow up to 3 concurrent connections per account/IP.
- **Partitioning Strategy:** The 2,477 maritime bounding boxes are divided evenly into 3 worker streams (~825 boxes each). This reduces the JSON subscription payload from an unstable ~102 KB down to ~33 KB, well within standard WebSocket frame constraints.
- **Staggered Handshakes:** Workers stagger their initial connection attempts by `1.5s` (`Worker 0` at 0s, `Worker 1` at 1.5s, `Worker 2` at 3.0s) to prevent concurrent handshake rate-limiting (HTTP 429).
- **Keepalive Tuning:** Connections use `ping_interval=30.0`, `ping_timeout=30.0`, `close_timeout=10.0`, and `max_size=None` to prevent premature disconnections from proxy latency.
- **Independent Self-Healing:** Each worker catches connection drops and reconnects independently using exponential backoff without disrupting the other two streams.

### 2. 20-Second Upfront Telemetry Warm-Up Gate
- **Purpose:** Aggregates a baseline fleet snapshot across all 2,477 ports before user interaction so newly monitored ports immediately have live vessel counts.
- **Deduplicated Snapshot Flush:** When the 20-second warm-up elapses, `flush_stream_snapshot_to_cache()` persists active vessel counts into SQLite. It enforces `seen_port_ids = set()` to prevent duplicate insertions when ports are indexed under both their ID (`port-nlrtm`) and LOCODE (`NLRTM`).
- **Continuous 24/7 Monitoring:** The stream manager does **not** stop after warm-up. It keeps listening 24/7. Incoming vessel pings continuously update in-memory positions, speeds, and timestamps. Silent vessels (>30 minutes without a ping) are automatically pruned.

### 3. User Login & Warm-Up Spinner Flow
- The user lands on the **Login Screen** immediately (`!user`).
- Upon entering an email address, if the 20-second warm-up is still active in the backend, the client presents a clean loading spinner: *"Loading Port Data — Collecting live satellite AIS vessel telemetry across global maritime ports. Entering dashboard momentarily..."* (no countdown numbers).
- Once `streamStatus.isWarmingUp` flips to `false`, the user seamlessly transitions into their dashboard.

---

## 6. Risk Engine & Vessel Profiling Specifications

### 1. Vessel Taxonomy & Design Drafts
Berthmark models 13 distinct commercial vessel classes with industry-standard design drafts:

| Sector | Vessel Class ID | Display Label | Design Draft |
| :--- | :--- | :--- | :--- |
| **Container** | `feeder` | Feeder Container (<3,000 TEU) | 9.5 m |
| **Container** | `panamax` | Panamax Container (3,000–5,100 TEU) | 12.5 m |
| **Container** | `neoPanamax` | Neo-Panamax Container (10,000–14,500 TEU) | 15.2 m |
| **Container** | `ulcv` | Ultra Large Container Vessel (ULCV >18,000 TEU) | 16.5 m |
| **Liquid Bulk** | `mrTanker` | Medium Range (MR) Product Tanker | 11.0 m |
| **Liquid Bulk** | `aframax` | Aframax Crude Tanker (80k–120k DWT) | 14.8 m |
| **Liquid Bulk** | `suezmax` | Suezmax Crude Tanker (120k–200k DWT) | 17.0 m |
| **Liquid Bulk** | `vlcc` | VLCC / ULCC Supertanker (>200k DWT) | 20.5 m |
| **Dry Bulk** | `handysize` | Handysize / Supramax Bulk Carrier | 10.5 m |
| **Dry Bulk** | `panamaxBulk` | Panamax Dry Bulk Carrier | 14.0 m |
| **Dry Bulk** | `capesize` | Capesize Bulk Carrier (>100k DWT) | 18.0 m |
| **Specialized** | `pctc` | Pure Car/Truck Carrier (PCTC / Ro-Ro) | 10.0 m |
| **Specialized** | `lng` | LNG / LPG Gas Carrier | 12.0 m |

### 2. Multi-Factor Risk Assessment Rules

#### A. Navigational Risk (PIANC Under-Keel Clearance)
- **Calculation:** $\text{UKC} = \text{Channel Depth (m)} - \text{Vessel Design Draft (m)}$.
- **High Risk:** $\text{UKC} < 1.0\,\text{m}$ (critical grounding hazard).
- **Medium Risk:** $1.0\,\text{m} \le \text{UKC} < 2.0\,\text{m}$ (marginal operating window).
- **Low Risk:** $\text{UKC} \ge 2.0\,\text{m}$ (safe passage).

#### B. Congestion Risk (Rolling 30-Day Historical Average)
- **Surge Ratio:** $\text{Queue Ratio} = \frac{\text{Current Live Anchored/Stationary Vessels}}{\text{30-Day Average Anchored Vessels}}$.
- **High Risk:** $\text{Queue Ratio} \ge 1.5$ **OR** $\ge 25$ stationary vessels waiting.
- **Medium Risk:** $\text{Queue Ratio} \ge 1.2$ **OR** $\ge 12$ stationary vessels waiting.
- **Low Risk:** $\text{Queue Ratio} < 1.2$ and $< 12$ vessels waiting.
- **Cold-Start Rule:** If zero historical snapshots exist in SQLite, the first observed count serves as the initial baseline ($\text{Ratio} = 1.0$), ensuring new ports start in a neutral state without synthetic numbers.

#### C. Weather Risk (Open-Meteo Telemetry)
Evaluates sustained wind speeds, peak gusts, wave heights, and visibility against vessel-class specific limits (e.g., Feeder threshold: 22 kn wind, 1.8 m waves; ULCV threshold: 30 kn wind, 2.8 m waves).
- **High Risk:** Wave height or wind speed exceeding high thresholds, or visibility $< 1.5\,\text{NM}$.
- **Medium Risk:** Weather approaching operational limits, or visibility $< 3.0\,\text{NM}$.
- **Low Risk:** Conditions comfortably below operational limits.

#### D. Composite Risk (Weakest-Link Rule)
- $\text{Composite} = \max(\text{Navigational}, \text{Congestion}, \text{Weather})$.
- If **any** sub-category is High $\rightarrow$ Composite is **High**.
- If no Highs, but **any** sub-category is Medium $\rightarrow$ Composite is **Medium**.
- Only if **all three** sub-categories are Low $\rightarrow$ Composite is **Low**.

---

## 7. Notification Routing, Anti-Flapping & Email Delivery

Berthmark features automated email and in-app alerting to keep operators informed of risk state changes:

1. **User-Bound Alert Routing:** The email entered during authentication automatically serves as the delivery address for that user's port alerts.
2. **Subscription Baseline Confirmation:** When an operator subscribes to monitor a port, an immediate welcome/baseline email is dispatched containing current weather, queue size, and composite risk tier.
3. **Warm-Up Warning Suppression:** Automated congestion and weather warning emails are suppressed during the 20-second warm-up window to prevent false alarms while baseline queues populate.
4. **30-Minute Rate-Limiting Cooldown:** Warning notifications are throttled to at most **one email per port every 30 minutes** (`COOLDOWN_SECONDS = 1800.0`). State flaps (e.g. rapid Medium $\leftrightarrow$ High oscillations) record in the in-app notification center but do not trigger email spam.
5. **Per-Port Notification Opt-Out:** Users can toggle notifications on or off per port via `PATCH /api/v1/ports/{portId}/notifications`.
6. **Demo Account Protection:** Accounts with demo domains (`@pacific-shipping.com`, `@rotterdam-logistics.nl`, `@globalmaritime.org`, `@example.com`) suppress real outbound SMTP to avoid deliverability penalties, logging the formatted email to the backend console.

---

## 8. Multi-Tier Caching Specifications

To balance real-time telemetry with API rate limits, Berthmark enforces strict caching lifetimes:

| Component | Layer | Storage Medium | TTL | Invalidation / Bypass |
| :--- | :--- | :--- | :--- | :--- |
| **Marine Weather** | Backend | SQLite `external_weather_cache` + Memory | 30 Minutes | `force_refresh=True` |
| **AIS Vessel Traffic**| Backend | SQLite `external_ais_traffic_cache` + Memory | 30 Minutes | `force_refresh=True` |
| **Risk Assessment** | Backend | Memory (`_assessment_cache`) | 5 Minutes | `forceRefresh=true` query param |
| **Historical Trends**| Backend | Memory (`_trend_cache`) | 5 Minutes | `forceRefresh=true` query param |
| **Port Search** | Frontend | Memory cache | 5 Minutes | Automatic invalidation on search |

---

## 9. Developer Setup & Workflow Commands

The project uses GNU `make` for consistent, cross-environment task automation:

```bash
# 1. Install all dependencies and setup environment
make install           # Sets up backend/.venv, imports unlocode.db, installs npm packages

# 2. Database Management
make seed-db           # Imports/re-indexes UN/LOCODE & NGA Pub 150 database
make reset-db          # Deletes user database and caches (berthmark.db) for a clean slate
make clean-all         # Removes build artifacts, caches, and user database

# 3. Running Applications
make dev               # Runs backend (port 8000) and frontend (port 5173) concurrently
make run-backend       # Starts FastAPI server standalone on http://localhost:8000
make run-frontend      # Starts React Vite client standalone on http://localhost:5173

# 4. Verification & Testing
make test              # Runs both backend pytest suite and frontend vitest suite
make test-backend      # Runs backend pytest suite (61 tests)
make test-frontend     # Runs frontend vitest suite (42 tests)
make test-apis         # Executes live diagnostic connectivity check against external APIs
make build             # Compiles frontend production bundle to frontend/dist
```

### Environment Configuration (`backend/.env`)
```env
# Database URL (SQLite default, PostgreSQL supported)
DATABASE_URL=sqlite:///backend/data/berthmark.db

# Live AISStream WebSocket API Key (aisstream.io)
AISSTREAM_API_KEY=your_key_here

# Outbound SMTP Configuration (Optional: console fallback if empty)
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=alerts@berthmark.com

# Ingestion Intervals
ENABLE_INGESTION=True
INGESTION_INTERVAL_MINUTES=30
```

---

## 10. Strict Development Rules & Safety Guardrails

Any AI agent or software engineer contributing to this repository **must strictly abide by the following rules**:

1. **Maintain Codebase Decoupling:**
   - Frontend and backend must remain strictly decoupled.
   - Frontend components must communicate exclusively through FastAPI REST endpoints. Never couple frontend code directly to database queries or server internals.
2. **Zero Fallback/Mock Data in Application Code:**
   - Never insert random number generators, simulated vessel metrics, or fake weather readings into production services or clients.
   - If an external reading is unavailable, handle the null state gracefully or report genuine errors.
3. **Preserve the Empty Portfolio Standard:**
   - Never inject default hubs or pre-populated ports into `PortService.get_ports(user_id)`.
   - New users must always start with an empty portfolio (`[]`).
4. **Respect Rate Limits & Stream Concurrency:**
   - Do not open more than 3 simultaneous WebSocket connections to AISStream.
   - Maintain staggered connection delays (`worker_id * 1.5s`) to prevent HTTP 429 rate limits.
   - Always enforce `seen_port_ids = set()` when persisting snapshot batches to prevent primary key collisions.
5. **Documentation Integrity:**
   - Preserve existing docstrings, technical rationale, and architectural commentary.
   - Keep markdown links formatted using GitHub-style `file://` URIs (e.g. `[ais_client.py](file:///path/to/ais_client.py)`).
6. **Incremental, Verified Changes:**
   - Make edits in small, testable increments.
   - Do not perform complete rewrites of large files when targeted replacements suffice.
   - Always verify that all 61 backend pytest tests and 42 frontend vitest tests pass before finalizing changes.
