# Berthmark: Maritime Port-Call Risk Intelligence Platform

Berthmark is a real-time maritime port-call risk assessment platform designed for ship operations managers, chartering desks, and fleet operators. It continuously monitors commercial ports globally, evaluating vessel-class-specific grounding hazards under PIANC safety standards, live and historical traffic congestion, local metocean weather, and terminal operational efficiency.

The platform surfaces proactive, ranked alternative port diversion recommendations when high risk is detected, backed by an inline, high-density dashboard and interactive SVG world map—built with zero flyout panels, slide-out drawers, or secondary hidden menus.

---

## Key Capabilities

- **Vessel-Class-Specific Risk Intelligence**: Evaluates grounding and navigational risk tailored to 13 benchmark commercial vessel classes (from Handysize bulkers to Ultra-Large Container Vessels and VLCCs) using physical draft and PIANC under-keel clearance constraints ($h_{\text{req}} = (1.30 \text{ to } 1.40) \times T_{\text{draft}}$).
- **Weakest-Link Composite Risk Engine**: Aggregates four sub-risk dimensions (**Navigational**, **Weather**, **Congestion**, and **Terminal**) into an overall tier (`LOW`, `MEDIUM`, `HIGH`) governed by the most critical vulnerability.
- **Automated Alternative Port Recommendations**: Dynamically gates candidate ports by physical channel depth ($WPI_{\text{channel\_depth}} \ge h_{\text{req}}$), regional subdivision proximity, and Haversine geodesic distance to deliver diversion suggestions directly inside high-risk cards and map popups.
- **Real-Time AIS Ingestion**: Connects to AISStream.io WebSockets partitioned across three regional worker pools (Americas, Europe/Africa/Middle East, Asia-Pacific) with dynamic point-offset bounding box geofences.
- **Metocean Weather Ingestion**: Ingests swell height ($H_s$), wave period ($T_p$), wind speed, and visibility forecasts from Open-Meteo.
- **Direct UI Philosophy**: All metrics, sub-risk score breakdowns, diversion recommendations, and on-map tooltips render directly on inline cards and popups for immediate situational awareness without multi-step navigation.

---

## Architecture & Tech Stack

```
berthmark/
├── backend/                  # FastAPI async backend
│   ├── ais/                  # Background AISStream WebSocket workers
│   ├── auth/                 # JWT authentication & operator management
│   ├── ingestion/            # UN/LOCODE & World Port Index (WPI) reconciliation
│   ├── ports/                # Port directory & user watchlist services
│   ├── routers/              # Risk assessment & notification endpoints
│   ├── schemas/              # Pydantic v2 domain schemas
│   ├── services/             # PIANC grounding, congestion, weather & risk engines
│   ├── taxonomy/             # Vessel benchmark taxonomy & PIANC parameters
│   ├── database.py           # SQLAlchemy 2.0 async engine & session management
│   ├── main.py               # Application entrypoint & dependency health checks
│   └── seed.py               # Unified idempotent seeder
├── frontend/                 # React 18 + Vite SPA
│   ├── src/
│   │   ├── components/       # Card grid, interactive map, notifications, dialogs
│   │   ├── services/         # HTTP API clients & mock fallback services
│   │   └── App.tsx           # Main workspace coordinating map, cards & alerts
│   ├── nginx.conf            # Production Nginx reverse proxy configuration
│   └── Dockerfile            # Multi-stage production container build
├── tests/                    # Pytest backend unit, integration & E2E suite
├── docker-compose.yml        # Multi-service stack (db, redis, backend, worker, frontend)
├── openapi.yaml              # Shared OpenAPI 3.0 API specification contract
└── pyproject.toml            # Python backend dependencies managed via uv
```

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
| `AISSTREAM_API_KEY` | Real-time AIS vessel position reports from [AISStream.io](https://aisstream.io). If omitted or blank, workers enter a safe idle standby mode. | `your_aisstream_api_key_here` |
| `DATABASE_URL` | SQLAlchemy async database connection string. Supports SQLite (`sqlite+aiosqlite:///`) or PostgreSQL (`postgresql+asyncpg://`). | `sqlite+aiosqlite:////app/berthmark.db` |
| `CACHE_URL` | Redis instance connection string for session and rate-limit caching. | `redis://localhost:6379` |
| `JWT_SECRET_KEY` | Secret key for signing HMAC-SHA256 JWT access tokens. | `berthmark-development-insecure-secret-key-change-in-production` |
| `JWT_ALGORITHM` | Token signing algorithm. | `HS256` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Lifetime of user access tokens. | `1440` (24 hours) |
| `PORT` | Backend HTTP API port. | `8000` |
| `NODE_ENV` | Runtime environment mode. | `development` or `production` |

### Default Operator Credentials

The database seeder automatically creates an initial Ship Operations Manager account:
- **Email**: `operator@maritimerisk.com`
- **Password**: `SampleSecurePassword123!`

---

## Running Locally

### Prerequisites

- **Python 3.11+** with [`uv`](https://docs.astral.sh/uv/) installed.
- **Node.js 20+** and `npm`.

### 1. Backend Setup

1. **Install dependencies**:
   ```bash
   uv sync
   ```

2. **Apply database migrations**:
   ```bash
   uv run alembic upgrade head
   ```

3. **Seed benchmark data**:
   Populates commercial vessel taxonomy, the default operator profile, and 168-hour traffic baselines:
   ```bash
   uv run python -m backend.seed
   ```

4. **Start the API server**:
   ```bash
   uv run uvicorn backend.main:app --reload --port 8000
   ```
   Interactive API documentation will be available at:
   - Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
   - Health Status: [http://localhost:8000/health](http://localhost:8000/health)

5. **(Optional) Run background AIS stream worker**:
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
   The dashboard will be accessible at [http://localhost:5173](http://localhost:5173).

---

## Running with Docker and Docker Compose

Berthmark includes a complete production-ready container stack managing PostgreSQL with PostGIS, Redis, the FastAPI backend, the AIS stream worker, and the React frontend behind Nginx.

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

Runs 141 unit, integration, and end-to-end user journey tests:
```bash
uv run pytest
```

### Frontend Vitest Suite & Typecheck

Runs 115 component and integration tests with strict TypeScript validation:
```bash
# Run unit & integration tests
npm --prefix frontend test

# Run TypeScript typecheck
npm --prefix frontend run typecheck

# Build production bundle
npm --prefix frontend run build
```

---

## Contributing & API Contract Guidelines

- **Dependencies**: All backend dependencies belong in [`pyproject.toml`](file:///home/tstewart/portfolio/ai-dev-tools-projects/berthmark/pyproject.toml) managed via `uv`. All frontend dependencies belong in [`frontend/package.json`](file:///home/tstewart/portfolio/ai-dev-tools-projects/berthmark/frontend/package.json).
- **API Parity**: Do not modify endpoint schemas without updating [`openapi.yaml`](file:///home/tstewart/portfolio/ai-dev-tools-projects/berthmark/openapi.yaml).
- **Direct UI Rule**: Do not introduce slide-out drawers, flyout menus, or collapsible bottom-sheets. All operational data must display inline in cards or on-map tooltip popups.
