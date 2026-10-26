# Berthmark: Maritime Port-Call Risk Intelligence Platform

Berthmark is a real-time maritime port-call risk intelligence and decision-support platform designed for ship operations managers, chartering desks, and fleet operators. It continuously monitors commercial ports globally, evaluating vessel-class-specific grounding hazards under PIANC safety standards, live and empirical AIS traffic congestion, local metocean weather conditions, and terminal operational efficiency.

The platform surfaces proactive, ranked alternative port diversion recommendations when elevated risk is detected, backed by an inline, high-density dashboard and interactive SVG world map—built with zero flyout panels, slide-out drawers, or secondary hidden menus.

---

## Key Capabilities

- **Vessel-Class-Specific Risk Intelligence**: Evaluates grounding and navigational safety tailored to 7 benchmark commercial vessel classes (Handymax/Supramax, Panamax, New Panamax, Aframax, Suezmax, VLCC, and ULCS) using physical draft and PIANC under-keel clearance constraints ($h_{\text{req}} = (1.30 \text{ to } 1.40) \times T_{\text{draft}}$).
- **Weakest-Link Composite Risk Engine**: Aggregates four operational sub-risk dimensions (**Navigational**, **Weather**, **Congestion**, and **Terminal**) into a composite tier (`LOW`, `MEDIUM`, `HIGH`) governed by the most critical vulnerability.
- **Empirical Baseline & Congestion Risk Engine**: Eliminates all synthetic or heuristic traffic numbers. When historical traffic baselines (`port_traffic_baselines`) have not yet accumulated for a given `(day_of_week, hour_of_day)` slot, the system sets `queue_variance_pct` to `null` (rendered in the UI as `"N/A — Collecting Baseline"`) and evaluates Congestion Risk strictly using live anchored vessel count thresholds ($0\text{--}5 = \text{LOW}$, $6\text{--}15 = \text{MEDIUM}$, $>15 = \text{HIGH}$). Baselines are populated solely by real AIS position reports accumulated over time via true rolling averages.
- **Automated Alternative Port Recommendations**: Dynamically gates candidate ports by physical channel depth ($WPI_{\text{channel\_depth}} \ge h_{\text{req}}$), regional subdivision proximity, and Haversine geodesic distance to deliver diversion suggestions directly inside high-risk cards and map popups.
- **Real-Time AIS & Metocean Feeds**: Connects to AISStream.io WebSockets partitioned across regional worker pools with dynamic point-offset bounding box geofences, alongside real-time metocean forecasts (swell height $H_s$, wave period $T_p$, wind speed, and visibility) via Open-Meteo.
- **Self-Service Authentication & Private Watchlists**: Supports self-service user registration (`POST /api/auth/register`, `/signup` route) with secure bcrypt password hashing and JWT access tokens. Authenticated users manage private port watchlists while guest visitors access default benchmark ports.
- **Direct UI Philosophy**: All metrics, sub-risk score breakdowns, diversion recommendations, and on-map tooltips render directly on inline cards and popups for immediate situational awareness without multi-step navigation.

---

## Architecture & Tech Stack

```
berthmark/
├── backend/                  # FastAPI async backend
│   ├── ais/                  # Background AISStream WebSocket workers & geofence manager
│   ├── auth/                 # JWT security, bcrypt hashing, registration & auth routers
│   ├── ingestion/            # UN/LOCODE & World Port Index (WPI) reconciliation logic
│   ├── ports/                # Port directory, search & user watchlist services
│   ├── routers/              # Risk assessment & notification API endpoints
│   ├── schemas/              # Pydantic v2 domain & API schemas
│   ├── services/             # PIANC grounding, congestion, weather & risk engines
│   ├── taxonomy/             # 7 benchmark vessel classes & PIANC parameters
│   ├── database.py           # SQLAlchemy async ORM, schema auto-init & bulk seeder
│   ├── main.py               # Application entrypoint & dependency health checks
│   └── seed.py               # Standalone idempotent seeder
├── frontend/                 # React 18 + Vite SPA (TypeScript, Tailwind CSS, Lucide)
│   ├── src/
│   │   ├── components/       # Card grid, interactive map, notifications, sign-up/login
│   │   ├── context/          # AuthContext for session management
│   │   ├── services/         # HTTP API clients & fallback services
│   │   └── App.tsx           # Main workspace coordinating map, cards, alerts & routes
│   ├── nginx.conf            # Production Nginx reverse proxy configuration
│   └── Dockerfile            # Multi-stage production container build
├── scripts/
│   └── build_seed_data.py    # Offline dataset ETL (WPI + UN/LOCODE -> ports_seed.json)
├── app/
│   └── data/
│       └── ports_seed.json   # Reconciled global port seed dataset (7,300+ ports)
├── tests/                    # Pytest backend unit, integration & E2E suite
├── docker-compose.yml        # Multi-service stack (db, redis, backend, worker, frontend)
├── openapi.yaml              # Shared OpenAPI 3.0 API specification contract
└── pyproject.toml            # Python backend dependencies managed via uv
```

---

## Offline Dataset ETL & Auto-Initialization Pipeline

### 1. Offline Dataset ETL (`scripts/build_seed_data.py`)

A standalone Python ETL script reconciles the local UN/LOCODE dataset and the National Geospatial-Intelligence Agency (NGA) World Port Index (WPI):

- **Primary Join**: Inner-joins WPI and UN/LOCODE records on WPI's 5-character `unlocode` attribute (`reconciliation_method = "EXACT_UNLOCODE"`).
- **Secondary Fuzzy/Spatial Match**: For WPI records missing explicit UN/LOCODE tags, performs fuzzy string matching on port names combined with geodesic proximity ($\le 10\text{ km}$) and matching ISO country codes (`reconciliation_method = "FUZZY_SPATIAL"`).
- **Depth Availability**: Sets `is_depth_available = true` when channel or anchorage depths are populated.
- **Export**: Generates [`app/data/ports_seed.json`](file:///home/tstewart/portfolio/ai-dev-tools-projects/berthmark/app/data/ports_seed.json) (7,300+ verified maritime ports).

To manually rebuild the seed dataset:
```bash
python scripts/build_seed_data.py
```

### 2. Database Auto-Initialization & Seeding on Boot

On backend startup, [`auto_init_database`](file:///home/tstewart/portfolio/ai-dev-tools-projects/berthmark/backend/database.py) runs automatically:

1. **Auto-Schema Creation**: Executes `Base.metadata.create_all()` to ensure all required tables (`ports`, `vessel_classes`, `users`, `user_watchlists`, `port_traffic_baselines`, `port_risk_snapshots`, `alert_logs`) exist.
2. **Automated Bulk Seed Check**: Runs `SELECT COUNT(*) FROM ports;`:
   - If `COUNT == 0` (fresh database): Bulk-inserts [`app/data/ports_seed.json`](file:///home/tstewart/portfolio/ai-dev-tools-projects/berthmark/app/data/ports_seed.json) into `ports` and seeds the 7 benchmark vessel classes into `vessel_classes`.
   - If `COUNT > 0`: Skips seeding instantly, ensuring zero-latency reboots.
3. **No Hardcoded Accounts**: The database initializes with 0 hardcoded operator accounts. All users register dynamically via the self-service registration workflow.

---

## API Keys & Environment Variables

Berthmark uses a Bring-Your-Own-Key (BYOK) architecture for external live feeds.

### Configuration Template

Copy the provided [`.env.example`](file:///home/tstewart/portfolio/ai-dev-tools-projects/berthmark/.env.example) to create your local `.env`:

```bash
cp .env.example .env
```

### Environment Variables Reference

| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `DATABASE_URL` | SQLAlchemy async database connection string. Supports SQLite (`sqlite+aiosqlite:///`) and PostgreSQL (`postgresql+asyncpg://`). | `sqlite+aiosqlite:///./berthmark.db` |
| `AISSTREAM_API_KEY` | Real-time AIS vessel position reports from [AISStream.io](https://aisstream.io). If omitted or blank, workers operate in safe standby mode. | `your_aisstream_api_key_here` |
| `CACHE_URL` | Redis connection string for caching and rate limiting. | `redis://localhost:6379` |
| `JWT_SECRET_KEY` | Secret key for signing HMAC-SHA256 JWT access tokens. | `berthmark-development-insecure-secret-key-change-in-production` |
| `JWT_ALGORITHM` | Token signing algorithm. | `HS256` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Lifetime of user access tokens. | `1440` (24 hours) |
| `PORT` | Backend HTTP API port. | `8000` |
| `NODE_ENV` | Runtime environment mode. | `development` or `production` |

---

## Self-Service Authentication & Watchlist Management

Berthmark features a self-service authentication workflow:

- **Registration (`/signup` Route & `POST /api/auth/register`)**: New users register with their Name, Email, and Password. Passwords are securely hashed with bcrypt. Upon successful registration, a signed JWT token is issued, the user is authenticated immediately, and lands on the dashboard with an empty custom watchlist.
- **Login (`POST /api/auth/login`)**: Registered users log in with their email and password to access their saved private watchlists.
- **Guest View**: Unauthenticated visitors view default commercial benchmark ports (Rotterdam, Singapore, Houston, Shanghai, Antwerp-Bruges) and can sign in or sign up at any time from the top navigation bar.

---

## Running Locally

### Prerequisites

- **Python 3.11+** with [`uv`](https://docs.astral.sh/uv/) installed.
- **Node.js 20+** and `npm`.

### 1. Backend Setup

1. **Install backend dependencies**:
   ```bash
   uv sync
   ```

2. **Start the API server**:
   ```bash
   uv run uvicorn backend.main:app --reload --port 8000
   ```
   *Note: Database tables and reference seed data are created automatically on boot.*

   Interactive API documentation will be available at:
   - **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
   - **Health Status**: [http://localhost:8000/health](http://localhost:8000/health)

3. **(Optional) Start the background AIS stream worker**:
   ```bash
   uv run python -m backend.ais.stream_worker
   ```

### 2. Frontend Setup

1. **Install frontend dependencies**:
   ```bash
   npm --prefix frontend install
   ```

2. **Start the Vite development server**:
   ```bash
   npm --prefix frontend run dev
   ```
   The dashboard will be accessible at [http://localhost:5173](http://localhost:5173). Navigate to [http://localhost:5173/signup](http://localhost:5173/signup) to create an account.

---

## Running with Docker and Docker Compose

Berthmark includes a production-ready container stack managing PostgreSQL with PostGIS, Redis, the FastAPI backend, the AIS stream worker, and the React frontend behind Nginx.

### Prerequisites

- **Docker 24.0+**
- **Docker Compose v2.20+**

### 1. Launch the Full Stack

```bash
# 1. Copy environment configuration
cp .env.example .env

# 2. Build and launch all services in detached mode
docker compose up --build -d
```

### 2. Service Endpoints

| Service | Container Name | Host Port | Internal Port | URL |
| :--- | :--- | :--- | :--- | :--- |
| **Frontend Web App** | `berthmark-frontend` | `80` | `80` | [http://localhost](http://localhost) |
| **Backend API** | `berthmark-backend` | `8000` | `8000` | [http://localhost:8000/docs](http://localhost:8000/docs) |
| **PostgreSQL + PostGIS** | `berthmark-db` | `5432` | `5432` | `localhost:5432` |
| **Redis Cache** | `berthmark-redis` | `6379` | `6379` | `localhost:6379` |
| **AIS Stream Worker** | `berthmark-worker` | — | — | Background Process |

### 3. Container Management Commands

- **Check running services and health status**:
  ```bash
  docker compose ps
  ```
- **Stream service logs**:
  ```bash
  docker compose logs -f
  ```
- **Stop containers**:
  ```bash
  docker compose down
  ```
- **Stop containers and purge persistent data volumes**:
  ```bash
  docker compose down -v
  ```

---

## Running Tests & Verification

### Backend Pytest Suite

Executes 146 unit, integration, and end-to-end user journey tests:
```bash
uv run pytest
```

### Frontend Vitest Suite & Production Build

Executes 125 component, context, routing, and integration tests with strict TypeScript compilation:
```bash
# Run Vitest test suite (13 test files)
npm --prefix frontend test

# Run TypeScript typecheck
npm --prefix frontend run typecheck

# Build production bundle
npm --prefix frontend run build
```

---

## Contributing & API Contract Guidelines

- **Dependencies**: Dependencies belong in [`pyproject.toml`](file:///home/tstewart/portfolio/ai-dev-tools-projects/berthmark/pyproject.toml) (backend) and [`frontend/package.json`](file:///home/tstewart/portfolio/ai-dev-tools-projects/berthmark/frontend/package.json) (frontend). Do not add dependencies without authorization.
- **API Contract Parity**: Do not modify endpoint structures without updating [`openapi.yaml`](file:///home/tstewart/portfolio/ai-dev-tools-projects/berthmark/openapi.yaml).
- **Direct UI Rule**: Do not introduce slide-out drawers, flyout menus, or collapsible bottom-sheets. All operational data must display inline in cards or on-map tooltip popups.
- **Git Commits**: Commit code regularly to Git after completing logical sub-tasks.
