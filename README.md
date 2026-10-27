# Berthmark

Real-time maritime port-call risk intelligence and operational decision-support platform for fleet operators, chartering desks, and port authorities.

Berthmark dynamically evaluates port safety constraints against international engineering guidelines (PIANC Report 121), real-time marine weather, Under-Keel Clearance (UKC) margins, and live AIS vessel traffic congestion. When risk escalates to High, the platform automatically discovers and ranks viable alternative ports in the same regional jurisdiction.

---

## Key Features

- **Multi-Class Port Subscriptions**: Monitor ports under specific vessel classes (*VLCC, Suezmax, Aframax, Neo-Panamax, Panamax, Handymax/Supramax, etc.*) or subscribe to the same port under multiple classes to compare draft margins side by side.
- **Global Port Directory**: Reconciled dataset of **2,890+ commercial ports** integrating UN/LOCODE keys and NGA World Port Index (Pub 150) controlling channel depths.
- **Physics-Grounded Grounding Risk**: PIANC Report 121 Under-Keel Clearance formulas evaluating channel depths against dynamic vessel draft and wave swell.
- **Automated Alternative Port Diversions**: Automatic Haversine geodesic proximity ranking and depth gating for safe candidate diversion ports when primary ports reach High risk.
- **Direct UI Philosophy**: High-density card grid and interactive SVG map popups displaying 4D traffic counts, weather, UKC margins, and telemetry directly without slide-out drawers.
- **Self-Service Authentication**: User registration and JWT-based session security with isolated watchlists.

---

## Running Locally

### Prerequisites
- **Python 3.11+** with [`uv`](https://docs.astral.sh/uv/) installed
- **Node.js 20+** and `npm`

### 1. Backend Setup

```bash
# 1. Install Python dependencies
uv sync

# 2. Seed database (populates 2,890+ global ports and benchmark vessel classes)
uv run python -m backend.seed

# 3. Start the FastAPI server
uv run uvicorn backend.main:app --reload --port 8000
```

* **Swagger API Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

*(Optional) Start the live AISStream worker:*
```bash
uv run python -m backend.ais.stream_worker
```

### 2. Frontend Setup

```bash
# 1. Install Node dependencies
npm --prefix frontend install

# 2. Launch Vite development server
npm --prefix frontend run dev
```

* **Web Application**: [http://localhost:5173](http://localhost:5173)
* Sign up for an account at [http://localhost:5173/signup](http://localhost:5173/signup) to create your custom watchlist.

---

## Running with Docker

Berthmark includes a complete `docker-compose` stack (PostgreSQL with PostGIS, Redis, FastAPI backend, AIS stream worker, and React frontend served via Nginx).

### Prerequisites
- **Docker 24.0+** & **Docker Compose v2.20+**

### Launch

```bash
# 1. Copy environment variables (optional: add your AISStream.io API key)
cp .env.example .env

# 2. Build and start containers
docker compose up --build -d
```

### Service URLs
| Service | URL |
| :--- | :--- |
| **Frontend Application** | [http://localhost](http://localhost) |
| **Backend Swagger API** | [http://localhost:8000/docs](http://localhost:8000/docs) |
| **PostgreSQL Database** | `localhost:5432` |
| **Redis Cache** | `localhost:6379` |

### Management Commands
```bash
# View running services
docker compose ps

# Follow container logs
docker compose logs -f

# Stop containers
docker compose down

# Stop containers and remove persistent volumes
docker compose down -v
```

---

## Running Tests

### Backend Tests (Pytest)
```bash
uv run pytest
```

### Frontend Tests (Vitest)
```bash
# Run unit & component tests
npm --prefix frontend run test -- --run

# Build production bundle
npm --prefix frontend run build
```

---

## Environment Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `DATABASE_URL` | SQLAlchemy async connection string (SQLite or PostgreSQL) | `sqlite+aiosqlite:///./berthmark.db` |
| `AISSTREAM_API_KEY` | API key from [AISStream.io](https://aisstream.io) for live vessel traffic | *(Optional / blank for standby)* |
| `CACHE_URL` | Redis connection URL | `redis://localhost:6379` |
| `JWT_SECRET_KEY` | Secret key for JWT session tokens | *(Configurable secret string)* |
| `PORT` | API server port | `8000` |
