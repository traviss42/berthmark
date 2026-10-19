# Real-Time Maritime Port-Call Risk Intelligence & Operational Monitoring MVP
## Complete Project Specification & Architecture Plan (`plan.md`)

---

## Executive Summary & Core Purpose
* **Project Name**: Real-Time Maritime Port-Call Risk Intelligence & Operational Monitoring Platform (MVP)
* **Target Audience**: Ship operators, charterers, fleet managers, and port authorities.
* **Core Value Proposition**: Dynamically monitor real-time navigational depth constraints, wave/swell hazards, port anchorage queues, and weather risks across global commercial ports. When a primary port experiences critical navigational restrictions or heavy congestion, the platform automatically identifies and ranks viable alternative ports in the same regional jurisdiction.

---

## 1. System Scope & Operational Design

### 1.1 Operational Focus
* **Regional Port Risk & Alternative Port Discovery**: Focuses on monitoring designated commercial port locations selected by the user, dynamically calculating risk profiles based on the specific vessel class assigned to each port.

### 1.2 Vessel Targeting Strategy
* **Standard Commercial Vessel Classes**: Evaluates ports against benchmark vessel categories rather than tracking individual ship IMO/MMSI numbers.
* **Supported Vessel Benchmark Classes**:
  * **Handymax / Supramax**: Draft $\sim 10.0\text{ m} - 11.5\text{ m}$, Beam $\sim 28\text{ m} - 32\text{ m}$
  * **Panamax**: Draft $\sim 12.0\text{ m} - 13.5\text{ m}$, Beam $\sim 32.2\text{ m}$
  * **New Panamax (Neopanamax)**: Draft $\sim 15.2\text{ m}$, Beam $\sim 49\text{ m}$, LOA $\sim 366\text{ m}$
  * **Aframax**: Draft $\sim 14.5\text{ m} - 15.0\text{ m}$, Beam $\sim 44\text{ m}$
  * **Suezmax**: Draft $\sim 16.0\text{ m} - 17.0\text{ m}$, Beam $\sim 50\text{ m}$
  * **VLCC (Very Large Crude Carrier)**: Draft $\sim 20.0\text{ m} - 21.5\text{ m}$, Beam $\sim 60\text{ m}$
  * **ULCS / Very Large Container Ship**: Draft $\sim 15.5\text{ m} - 16.5\text{ m}$, Beam $\sim 59\text{ m}$

### 1.3 Flexible Per-Port Vessel Subscription
* Users assign a specific vessel class to each port in their watchlist.
* **Multi-Class Multi-Port Capability**: Users can subscribe to the same port multiple times under different ship classes (e.g., *Port of Rotterdam – VLCC* and *Port of Rotterdam – Handymax*) to compare class-specific depth and swell accessibility margins side by side.

---

## 2. Integrated Data Sources & Reconciliation Pipeline

| Data Source | Type & Format | Core Fields Utilized | Operational Purpose in MVP |
| :--- | :--- | :--- | :--- |
| **UN/LOCODE** *(UNECE Rec. 16)* | CSV / Database Directory | `Country` (ISO 3166-1 alpha-2), `Location` (3-char code), `Subdivision` (ISO 3166-2), `Function`, `Coordinates` | Standardized 5-character port keys (e.g., `NLRTM`), location search auto-completion, and regional alternative search grouping. |
| **World Port Index (WPI)** *(NGA Pub 150)* | Database / Data Dictionary | `wpinumber`, `latitude`, `longitude`, `channel_de` (Channel Depth), `cargo_pier` (Cargo Pier Depth), `anchorage_` (Anchorage Depth), `entrance_w`, `unlocode` | Primary physical port reference providing controlling channel depths, anchorage depths, and entrance physical constraints. |
| **PIANC Guidelines (2014)** | Engineering Standards Document | Under-Keel Clearance (UKC) principles, Depth-to-Draft ($h/T$) multipliers, Squat ($S_{max}$) & Wave motion allowances | Physics-grounded safety ratios determining grounding risk based on vessel draft, channel depth, and wave swell height. |
| **Open-Meteo Marine & Weather API** | HTTP REST / JSON | `significant_wave_height` ($H_s$), `wave_period` ($T_p$), `wind_speed_10m`, `wind_gusts`, `visibility` | Continuous real-time marine weather and oceanographic swell hazard streaming (no API key required). |
| **AISStream.io API** | WebSocket Stream / JSON | `PositionReport` events: `MetaData.ShipName`, `MetaData.Latitude`, `MetaData.Longitude`, `Message.PositionReport.Sog` | Streaming live ship position reports within spatial anchorage bounding boxes to track real-time anchorage queues. |

### 2.1 Dataset Reconciliation Strategy (WPI <-> UN/LOCODE)
To eliminate missing data gaps (e.g., UN/LOCODE entries lacking WPI physical depths or WPI records lacking UN/LOCODE regional codes):
1. **Primary Join**: Inner-join WPI and UN/LOCODE using WPI's built-in `unlocode` attribute field.
2. **Secondary Spatial / Fuzzy Match**: For WPI ports missing explicit UN/LOCODE tags, perform a fuzzy string match on port names combined with distance proximity ($\le 10\text{ km}$) and matching ISO country codes.
3. **Data Quality Flags**: Each port entry in the database is tagged with `is_depth_available = TRUE/FALSE` and `reconciliation_method = EXACT_UNLOCODE | FUZZY_SPATIAL`. Ports without verified controlling depth data display a warning indicator in the UI rather than triggering false grounding alarms.

---

## 3. Risk Calculation Engine & Scoring Rules

### 3.1 Grounding Depth Risk Module (PIANC Simplified Ratios)
Grounding risk evaluates whether controlling port channel depth ($WPI_{channel\_de}$) satisfies PIANC Under-Keel Clearance (UKC) multipliers under dynamic sea swell conditions:
* **Baseline Depth Requirement** (Sheltered / Inner Channel):
  $$h_{req} = 1.10 \times T_{draft}$$
* **Swell-Adjusted Requirement** (Outer Channel / Heavy Swell $H_s > 2.0\text{ m}$):
  $$h_{req} = (1.30 \text{ to } 1.40) \times T_{draft}$$
* **Risk Categorization**:
  * **LOW RISK (Green)**: $WPI_{channel\_de} \ge h_{req} + 1.0\text{ m}$ (Safe depth clearance margin)
  * **MEDIUM RISK (Yellow)**: $h_{req} \le WPI_{channel\_de} < h_{req} + 1.0\text{ m}$ (Tight clearance margin / tidal assistance required)
  * **HIGH / CRITICAL RISK (Red)**: $WPI_{channel\_de} < h_{req}$ (Grounding hazard / Draft exceedance violation)

### 3.2 Congestion Risk Module (Anchorage Area Vessel Count)
Measures operational delay risk based on the number of stationary vessels waiting in outer anchorage bounding boxes:
* **AIS Filtering Rules**:
  * Low Speed Threshold: $\text{SOG} \le 0.5\text{ knots}$.
  * Spatial Boundary: Point-Offset Bounding Box centered on WPI port coordinates.
  * Sliding Window: Maintain in-memory set of unique MMSIs updated within a 15–20 minute rolling window. Purge MMSI if inactive for $> 20$ minutes.
* **Risk Categorization**:
  * **LOW CONGESTION (Green)**: $0 - 5$ ships anchored.
  * **MEDIUM CONGESTION (Yellow)**: $6 - 15$ ships anchored.
  * **HIGH CONGESTION (Red)**: $> 15$ ships anchored.

### 3.3 Atmospheric & Weather Hazard Module
* **High Wind Threshold**: Sustained wind speed $> 30\text{ knots}$ or gusts $> 40\text{ knots}$ (Restricts tug assistance & pilot boarding).
* **High Swell Threshold**: Significant wave height $H_s > 2.5\text{ m}$ (Triggers port entrance closure warnings).

### 3.4 Overall Risk Aggregation Model
* **Worst-Case Hazard Gating**:
  $$\text{Overall Port Risk} = \max(\text{Grounding Risk}, \text{Congestion Risk}, \text{Weather Risk})$$
* **Rule**: If any individual hazard triggers **HIGH / CRITICAL RISK**, the overall port status automatically escalates to **HIGH / CRITICAL RISK**, overriding lower scores in other categories.

---

## 4. Bounding Box Generation & AISStream WebSocket Connection Strategy

### 4.1 Simplified Point-Offset Bounding Box Generation
Since detailed port polygon geometry is absent in global datasets, bounding boxes are constructed dynamically from WPI point coordinates $(\text{Lat}, \text{Lon})$:
* **Bounding Box Formula**:
  * $\Delta \text{lat} = 0.10^\circ \approx 11\text{ km} \text{ (latitude offset)}$
  * $\Delta \text{lon} = \frac{0.10^\circ}{\cos(\text{Lat})} \text{ (longitude offset adjusted for latitude)}$
  * $\text{Lat}_{\text{min}} = \text{Lat} - \Delta \text{lat}, \quad \text{Lat}_{\text{max}} = \text{Lat} + \Delta \text{lat}$
  * $\text{Lon}_{\text{min}} = \text{Lon} - \Delta \text{lon}, \quad \text{Lon}_{\text{max}} = \text{Lon} + \Delta \text{lon}$
* **AISStream Payload Syntax**:
  ```json
  "BoundingBoxes": [
    [[lat_min, lon_min], [lat_max, lon_max]]
  ]
  ```

### 4.2 Demand-Driven Subscription Architecture
* **Active Watchlist Partitioning**: Rather than subscribing to all 3,000+ global ports simultaneously, the backend worker process maintains WebSocket bounding box subscriptions **only for ports currently present in active user watchlists**.
* **Three-Connection Worker Pool**: AISStream free-tier permits up to 3 open connections per account. Active port bounding boxes are divided across 3 regional connection processes:
  * **Connection Worker 1**: Americas & Atlantic Regions ($\text{Longitude } -180^\circ \text{ to } -30^\circ$)
  * **Connection Worker 2**: Europe, Africa & Middle East ($\text{Longitude } -30^\circ \text{ to } +60^\circ$)
  * **Connection Worker 3**: Asia-Pacific & Oceania ($\text{Longitude } +60^\circ \text{ to } +180^\circ$)

---

## 5. Automated Alternative Port Recommendation Engine

When a primary port's overall risk escalates to **HIGH** or **CRITICAL**, the recommendation engine executes the following dynamic pipeline:

1. **Regional Candidate Discovery**: Queries candidate ports sharing the primary port's **UN/LOCODE ISO 3166-2 Subdivision Code** (e.g., `NL-ZH` for South Holland) or adjacent coastal regions.
2. **Hard Physical Depth Constraint Gating**: Evaluates candidate ports against the assigned vessel class:
   $$\text{Filter out any candidate port where } WPI_{channel\_de} < h_{req}$$
3. **Distance-to-Primary Ranking**: Ranks surviving eligible candidate ports by geographic proximity to the primary port using the Haversine distance formula:
   $$d = 2r \arcsin\left(\sqrt{\sin^2\left(\frac{\Delta \phi}{2}\right) + \cos(\phi_1)\cos(\phi_2)\sin^2\left(\frac{\Delta \lambda}{2}\right)}\right)$$
4. **Output**: Presents a ranked list of candidate alternative ports complete with distance in Nautical Miles (NM), controlling channel depth, current swell height, and live risk badges.

---

## 6. UI / UX Architecture & Cold-Start Strategy

### 6.1 Port Search & Subscription Modal
* **Search Bar**: Auto-completes port queries by 5-character UN/LOCODE (e.g., `NLRTM`), port name (`"Rotterdam"`), or country subdivision.
* **Vessel Class Selector**: Dropdown menu allowing the user to pair the searched port with a specific ship class (Panamax, Aframax, VLCC, etc.).
* **Submit CTA**: Adds the subscription card to the user's dashboard and plots the port pin on the interactive map.

### 6.2 Main Dashboard Layout (Card Grid with Map Toggle)
* **Card Grid View (Default)**:
  * Cards automatically grouped by **Vessel Class** headers (e.g., *Panamax*, *VLCC*) or **UN/LOCODE Region**.
  * Each card displays:
    * Port Name, UN/LOCODE, Country Flag, Assigned Vessel Class.
    * Color-coded overall risk badge (Green / Yellow / Red).
    * Sub-hazard pill indicators: Depth Clearance Margin (m), Swell Height (m), Anchorage Queue Count.
* **Interactive Map View (Toggleable)**:
  * Full-screen interactive map displaying color-coded port markers at exact WPI coordinates.
  * **Slide-Out Inspection Drawer** (triggered on pin click):
    * Detailed sub-hazard breakdown graphs.
    * Live event log.
    * Ranked alternative port recommendations drawer.

### 6.3 Notification & Alert Architecture
* **Dynamic In-App Alert Feed**:
  * Top navigation bar notification bell with live counter.
  * Logs real-time risk state transitions (e.g., *\"Rotterdam – VLCC: Risk upgraded from LOW to HIGH due to 2.8m swell exceedance\"*).

### 6.4 Cold-Start & Initialization Handling
When a user subscribes to a new port:
1. **Instant Baseline (Depth & Weather)**: Grounding Depth Risk and Open-Meteo weather parameters load instantaneously from static database tables and HTTP REST queries.
2. **Cold-Start Queue Badge**: Congestion metric displays a pulsing **"Initializing Live Queue (Collecting AIS Pings)..."** indicator.
3. **10–15 Minute Accumulation Window**: The WebSocket worker aggregates pings over a 10–15 minute window (sufficient to capture stationary ships pinging on 3–6 minute intervals).
4. **Transition to Live Count**: The badge smoothly transitions to a live numeric queue count (e.g., *\"14 Ships Anchored — Medium Queue\"*).

---

## 7. First-Run User Journey (Walkthrough)

1. **Authentication & Empty State**:
   * User logs into the platform and lands on an empty Card Grid with an explicit call-to-action: **"+ Add First Port to Watchlist"**.
2. **Adding Port #1 (Rotterdam – VLCC)**:
   * User opens search modal, types `"NLRTM"` / `"Rotterdam"`, selects **Rotterdam (NL RTM)**, assigns **VLCC**, and clicks subscribe.
   * Card instantly loads depth and weather parameters; congestion displays *"Initializing Live Queue..."*.
3. **Adding Ports #2 & #3**:
   * User adds **Singapore (SG SIN)** under **New Panamax**, **Houston (US HOU)** under **Aframax**, and **Rotterdam (NL RTM)** a second time under **Handymax**.
4. **Clustered Dashboard View**:
   * Cards automatically cluster under vessel class headers (**VLCC**, **New Panamax**, **Aframax**, **Handymax**).
   * After 10–15 minutes, congestion badges populate live queue counts.
   * *Rotterdam – VLCC* displays **HIGH RISK (RED)** due to a 2.8m swell violating VLCC clearance, while *Rotterdam – Handymax* displays **LOW RISK (GREEN)** due to smaller draft.
5. **Interactive Map & Diversion Routing**:
   * User toggles to **Map View** and clicks the red Rotterdam pin.
   * Slide-out drawer opens, displaying sub-hazard breakdowns, the recent alert log, and a ranked list of candidate alternative ports in region `NL-ZH` that pass VLCC draft checks (e.g., *Wilhelmshaven – 140 NM*).

---

## 8. Local Setup & BYOK Environment Configuration (Phase 1 Focus)

### 8.1 Local Environment & BYOK Setup (Phase 1 MVP)
To get a local version running quickly and cleanly without container management overhead, credentials and local paths are managed via environment variables.

* **Local `.env` Configuration File**:
  ```env
  # AISStream Configuration (BYOK)
  AISSTREAM_API_KEY=your_aisstream_api_key_here

  # Local Development Settings
  PORT=8080
  NODE_ENV=development
  DATABASE_URL=postgresql://localhost:5432/maritime_risk
  CACHE_URL=redis://localhost:6379
  ```

* **Local Execution Flow**:
  1. Set up local database instance (PostgreSQL with PostGIS or SQLite/local DB).
  2. Run local data ingestion and stream worker script using `AISSTREAM_API_KEY`.
  3. Start local development web server to render cards, interactive maps, and alert feeds.

### 8.2 Future Roadmap: Containerization (Phase 2)
* **Future Enhancement Note**: Containerizing the application using Docker and Docker Compose is explicitly slated as a **Phase 2 enhancement**.
* Once the local MVP is fully verified, Docker builds can be introduced to package the database, stream worker, and web application into an easily deployable container stack.

---

## 9. Data Models & Database Schema

```sql
-- Reconciled Port Directory
CREATE TABLE ports (
    unlocode VARCHAR(5) PRIMARY KEY, -- e.g. 'NLRTM'
    port_name VARCHAR(100) NOT NULL,
    country_code CHAR(2) NOT NULL, -- ISO 3166-1
    subdivision_code VARCHAR(10) NOT NULL, -- ISO 3166-2 (e.g. 'NL-ZH')
    latitude DECIMAL(9, 6) NOT NULL,
    longitude DECIMAL(9, 6) NOT NULL,
    wpi_number INT UNIQUE,
    channel_depth_m DECIMAL(5, 2),
    cargo_pier_depth_m DECIMAL(5, 2),
    anchorage_depth_m DECIMAL(5, 2),
    is_depth_available BOOLEAN DEFAULT TRUE,
    reconciliation_method VARCHAR(20) DEFAULT 'EXACT_UNLOCODE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Vessel Class Benchmarks
CREATE TABLE vessel_classes (
    class_id VARCHAR(20) PRIMARY KEY, -- e.g. 'VLCC', 'PANAMAX'
    class_name VARCHAR(50) NOT NULL,
    draft_m DECIMAL(4, 2) NOT NULL,
    beam_m DECIMAL(4, 2) NOT NULL,
    loa_m DECIMAL(5, 2) NOT NULL
);

-- User Watchlist Subscriptions
CREATE TABLE user_watchlists (
    watchlist_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    unlocode VARCHAR(5) REFERENCES ports(unlocode),
    vessel_class_id VARCHAR(20) REFERENCES vessel_classes(class_id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, unlocode, vessel_class_id)
);

-- Dynamic Risk State Snapshots
CREATE TABLE port_risk_snapshots (
    snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    unlocode VARCHAR(5) REFERENCES ports(unlocode),
    vessel_class_id VARCHAR(20) REFERENCES vessel_classes(class_id),
    grounding_risk_level VARCHAR(10) CHECK (grounding_risk_level IN ('LOW', 'MEDIUM', 'HIGH')),
    congestion_count INT,
    congestion_risk_level VARCHAR(10) CHECK (congestion_risk_level IN ('LOW', 'MEDIUM', 'HIGH')),
    weather_risk_level VARCHAR(10) CHECK (weather_risk_level IN ('LOW', 'MEDIUM', 'HIGH')),
    overall_risk_level VARCHAR(10) CHECK (overall_risk_level IN ('LOW', 'MEDIUM', 'HIGH')),
    swell_height_m DECIMAL(4, 2),
    wind_speed_kts DECIMAL(4, 1),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Alert Notification Log
CREATE TABLE alert_logs (
    alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    unlocode VARCHAR(5) REFERENCES ports(unlocode),
    vessel_class_id VARCHAR(20) REFERENCES vessel_classes(class_id),
    previous_risk_level VARCHAR(10),
    new_risk_level VARCHAR(10),
    trigger_reason TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

*This specification serves as the consolidated master architecture plan (`plan-v5.md`) combining all technical data reconciliation, WebSocket partitioning, UI/UX cold-start walkthroughs, and local BYOK execution instructions.*
