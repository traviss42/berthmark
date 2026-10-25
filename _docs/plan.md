# Real-Time Maritime Port-Call Risk Intelligence & Operational Monitoring MVP
## Complete Project Specification & Architecture Plan (`plan.md`)

---

## Executive Summary & Core Purpose
* **Project Name**: Real-Time Maritime Port-Call Risk Intelligence & Operational Monitoring Platform (MVP)
* **Target Audience**: Ship operators, charterers, fleet managers, and port authorities.
* **Core Value Proposition**: Dynamically monitor real-time navigational depth constraints, wave/swell hazards, port anchorage queues, multi-state vessel traffic dynamics, and weather risks across global commercial ports through a simple, clean, direct interface. When a primary port experiences critical navigational restrictions or heavy congestion, the platform automatically identifies, gates, and ranks viable alternative ports in the same regional jurisdiction.

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
| **AISStream.io API** | WebSocket Stream / JSON | `PositionReport` events: `MetaData.ShipName`, `MetaData.Latitude`, `MetaData.Longitude`, `Message.PositionReport.Sog` | Streaming live ship position reports within spatial anchorage bounding boxes to track real-time vessel traffic dynamics. |

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

### 3.2 Congestion & Vessel Traffic Dynamics Module
Rather than relying solely on static anchorage counts, the congestion engine tracks four complementary traffic dimensions within each port's spatial bounding box:

1. **Anchored / Stationary Vessels**: Unique MMSIs with Speed Over Ground $\text{SOG} \le 0.5\text{ knots}$ waiting in outer anchorage zones or berths.
2. **Underway / Moving Vessels**: Unique MMSIs with $\text{SOG} > 0.5\text{ knots}$ actively maneuvering, transiting approach channels, or entering/exiting harbor boundaries.
3. **Total Active in Geofence**: Sum of all unique active MMSIs ($\text{Anchored} + \text{Underway}$) present inside the port's bounding box within the active sliding window.
4. **Historical Average Queue & Anomaly Detection**:
   * Maintains a rolling time-series baseline (7-day and 30-day moving average for the specific hour of the week) representing typical port activity ($N_{hist\_avg}$).
   * Calculates **Queue Variance Percentage**:
     $$\Delta Q_{pct} = \frac{N_{anchored} - N_{hist\_avg}}{N_{hist\_avg}} \times 100\%$$

* **Congestion Risk Categorization**:
  * **LOW CONGESTION (Green)**: $0 - 5$ ships anchored AND $\Delta Q_{pct} < +30\%$.
  * **MEDIUM CONGESTION (Yellow)**: $6 - 15$ ships anchored OR $\Delta Q_{pct} \in [+30\%, +75\%]$ above historical average.
  * **HIGH CONGESTION (Red)**: $> 15$ ships anchored OR $\Delta Q_{pct} > +75\%$ above historical baseline (signals severe queue anomaly / bottleneck).

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

### 4.2 Demand-Driven Subscription & Classification Worker Architecture
* **Active Watchlist Partitioning**: The backend worker process maintains WebSocket bounding box subscriptions **only for ports currently present in active user watchlists**.
* **Traffic State Classifier**:
  * On receiving `PositionReport`:
    * If $\text{SOG} \le 0.5\text{ kts}$, add MMSI to `anchored_mmsis` set with timestamp.
    * If $\text{SOG} > 0.5\text{ kts}$, add MMSI to `underway_mmsis` set with timestamp.
  * Maintain in-memory sliding window (15–20 min). Purge MMSI entries with no pings for $> 20$ minutes.
* **Three-Connection Worker Pool**: Active port bounding boxes are divided across 3 regional connection processes:
  * **Connection Worker 1**: Americas & Atlantic Regions ($\text{Longitude } -180^\circ \text{ to } -30^\circ$)
  * **Connection Worker 2**: Europe, Africa & Middle East ($\text{Longitude } -30^\circ \text{ to } +60^\circ$)
  * **Connection Worker 3**: Asia-Pacific & Oceania ($\text{Longitude } +60^\circ \text{ to } +180^\circ$)

---

## 5. Explicit Alternative Port Recommendation Engine Architecture

The **Automated Alternative Port Recommendation Engine** executes an explicit, multi-stage decision pipeline whenever a primary port's overall risk escalates to **HIGH** or **CRITICAL**.

### 5.1 Trigger Condition & Execution Flow
* **Automatic Execution**: Triggered automatically during the real-time risk snapshot update whenever:
  $$\text{overall\_risk\_level} \in (\text{'HIGH'}, \text{'CRITICAL'})$$
* **Purpose**: Provide ship operators and charterers with an immediate, pre-screened list of nearby commercial ports capable of safely receiving the specific assigned vessel class without operational or draft violations.

### 5.2 Dynamic Recommendation Pipeline Steps

1. **Step 1: Regional Candidate Discovery (UN/LOCODE ISO 3166-2 Matching)**
   * Queries the database for candidate commercial ports sharing the primary port's exact **UN/LOCODE ISO 3166-2 Subdivision Code** (e.g., `NL-ZH` for South Holland or `US-TX` for Texas) or designated adjacent coastal subdivisions.
   * **SQL Match Logic**:
     ```sql
     SELECT * FROM ports 
     WHERE subdivision_code = primary_port.subdivision_code 
       AND unlocode != primary_port.unlocode
       AND is_depth_available = TRUE;
     ```

2. **Step 2: Hard Physical Depth Constraint Gating (PIANC Safety Check)**
   * Evaluates each candidate port's controlling channel depth ($WPI_{channel\_de}$) against the assigned vessel class's dynamic Under-Keel Clearance requirement ($h_{req}$):
     $$h_{req} = (1.10 \text{ to } 1.40) \times T_{draft}$$
   * **Disqualification Rule**: Any candidate port where $WPI_{channel\_de} < h_{req}$ is immediately filtered out:
     $$\text{Filter out candidate IF } WPI_{channel\_de} < h_{req}$$
   * **Result**: Prevents recommending alternative ports where the vessel would risk grounding upon arrival.

3. **Step 3: Distance Proximity Ranking (Haversine Formula)**
   * For all surviving candidate ports that pass the depth clearance check, the engine computes exact nautical distance from the primary port using the Haversine formula:
     $$d = 2r \arcsin\left(\sqrt{\sin^2\left(\frac{\Delta \phi}{2}\right) + \cos(\phi_1)\cos(\phi_2)\sin^2\left(\frac{\Delta \lambda}{2}\right)}\right)$$
     *(where $r = 3,440.065 \text{ Nautical Miles}$, $\phi = \text{latitude in radians}$, $\lambda = \text{longitude in radians}$)*
   * Candidate ports are ordered in ascending order by distance ($d$).

4. **Step 4: Candidate Status & Weather Verification**
   * Fetches current Open-Meteo sea swell ($H_s$) and live risk snapshot for top candidate ports to ensure the alternative location itself is currently operating under **LOW** or **MEDIUM** risk.

5. **Step 5: Direct Interface Delivery (No Slide-Out Drawers)**
   * Outputs the top 3 ranked eligible candidate ports directly inside the primary port's dashboard card sub-section and in the interactive map tooltip popup.
   * **Displayed Alternative Attributes**:
     * Alternative Port Name & UN/LOCODE (e.g., *Wilhelmshaven – DE WVN*).
     * Proximity Distance in Nautical Miles (e.g., *140 NM*).
     * Controlling Channel Depth vs Required Draft Margin (e.g., *18.5m Depth / +3.0m Margin*).
     * Current Swell Height & Traffic Status (e.g., *1.2m Swell — LOW RISK*).

---

## 6. UI / UX Architecture & Direct Data Display (No Slide-Out Drawers)

### 6.1 Port Search & Subscription Modal
* **Search Bar**: Auto-completes port queries by 5-character UN/LOCODE (e.g., `NLRTM`), port name (`"Rotterdam"`), or country subdivision.
* **Vessel Class Selector**: Dropdown menu allowing the user to pair the searched port with a specific ship class (Panamax, Aframax, VLCC, etc.).
* **Submit CTA**: Adds the subscription card to the user's dashboard and plots the port pin on the interactive map.

### 6.2 Main Dashboard Layout (Card Grid with Map Toggle)
To keep the application simple and uncluttered while ensuring all key operational metrics remain immediately visible, all data fields are rendered directly within the cards and map popups—**no slide-out drawers or secondary hidden menus**:

* **Card Grid View (Default)**:
  * Cards automatically grouped by **Vessel Class** headers (e.g., *Panamax*, *VLCC*) or **UN/LOCODE Region**.
  * **Direct All-Value Card Layout**: Each card directly presents all key metrics in a clean, high-density format:
    * **Header**: Port Name, UN/LOCODE, Country Flag, Assigned Vessel Class.
    * **Overall Risk Badge**: Color-coded status (Green / Yellow / Red).
    * **Traffic Breakdown Values**: Anchored / Stationary Count, Underway Count, Total Geofence Active Count, and Historical Average Variance (e.g., *"18 Anchored / 8 Underway (26 Active) — +55% vs 7-day Avg"*).
    * **Depth & Weather Parameters**: Controlling Channel Depth, PIANC Draft Margin (m), Swell Height ($H_s$), Wind Speed.
    * **Inline Alternative Port Diversion Section**: If overall risk is High or Critical, a simple inline sub-card directly lists top eligible alternative ports with distance (NM) and depth clearance.
* **Interactive Map View (Toggleable)**:
  * Full-screen interactive map displaying color-coded port markers at exact WPI coordinates.
  * **Direct Map Tooltip / Popup Window**: Clicking a pin opens a clean map popup directly over the port pin displaying all metrics (traffic counts, weather, depth clearance, and alternative port recommendations) directly on screen without slide-out drawers.

### 6.3 Notification & Alert Architecture
* **Dynamic In-App Alert Feed**:
  * Top navigation bar notification bell with live counter.
  * Logs real-time risk state transitions (e.g., *"Rotterdam – VLCC: Congestion upgraded to HIGH (18 anchored, +65% above 7-day historical average)"*).

### 6.4 Cold-Start & Initialization Handling
When a user subscribes to a new port:
1. **Instant Baseline (Depth, Weather & Historical Avg)**: Grounding Depth Risk, Open-Meteo weather parameters, and historical baseline queue averages load instantaneously from database tables.
2. **Cold-Start Queue Badge**: Congestion metric displays a pulsing **"Initializing Live Traffic (Collecting AIS Pings)..."** indicator.
3. **10–15 Minute Accumulation Window**: The WebSocket worker aggregates pings over a 10–15 minute window to categorize anchored vs. underway vessels.
4. **Transition to Live Traffic Summary**: The badge smoothly transitions to live numeric counters (e.g., *"14 Anchored / 6 Underway (20 Active in Geofence — +25% vs Historical Avg)"*).

---

## 7. First-Run User Journey (Walkthrough)

1. **Authentication & Empty State**:
   * User logs into the platform and lands on an empty Card Grid with an explicit call-to-action: **"+ Add First Port to Watchlist"**.
2. **Adding Port #1 (Rotterdam – VLCC)**:
   * User opens search modal, types `"NLRTM"` / `"Rotterdam"`, selects **Rotterdam (NL RTM)**, assigns **VLCC**, and clicks subscribe.
   * Card instantly loads depth, weather parameters, and historical 7-day average queue baseline; live traffic displays *"Initializing Live Traffic..."*.
3. **Adding Ports #2 & #3**:
   * User adds **Singapore (SG SIN)** under **New Panamax**, **Houston (US HOU)** under **Aframax**, and **Rotterdam (NL RTM)** a second time under **Handymax**.
4. **Clustered Dashboard View**:
   * Cards automatically cluster under vessel class headers (**VLCC**, **New Panamax**, **Aframax**, **Handymax**).
   * After 10–15 minutes, live traffic badges populate:
     * *Rotterdam – VLCC*: Displays **18 Anchored, 8 Underway (26 Active in Geofence — +55% vs Historical Avg)** directly on the card.
     * Overall risk triggers **HIGH RISK (RED)** due to a 2.8m swell violating VLCC clearance AND elevated congestion variance.
     * *Rotterdam – Handymax*: Displays **LOW RISK (GREEN)** due to smaller draft clearance margin.
5. **Interactive Map & Diversion Routing**:
   * User toggles to **Map View** and clicks the red Rotterdam pin.
   * A direct map popup displays the complete traffic breakdown (18 Anchored / 8 Underway vs. 11.5 Historical Avg), depth clearance, swell height, and a ranked list of candidate alternative ports in region `NL-ZH` that pass VLCC draft checks (e.g., *Wilhelmshaven – 140 NM*)—all directly in the view without any slide-out drawers.

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

-- Historical Traffic Baseline Data (7-day / 30-day Moving Averages)
CREATE TABLE port_traffic_baselines (
    baseline_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    unlocode VARCHAR(5) REFERENCES ports(unlocode),
    day_of_week INT CHECK (day_of_week BETWEEN 0 AND 6), -- 0=Sun, 6=Sat
    hour_of_day INT CHECK (hour_of_day BETWEEN 0 AND 23),
    avg_anchored_count DECIMAL(5, 2) NOT NULL DEFAULT 0.0,
    avg_underway_count DECIMAL(5, 2) NOT NULL DEFAULT 0.0,
    avg_total_active DECIMAL(5, 2) NOT NULL DEFAULT 0.0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(unlocode, day_of_week, hour_of_day)
);

-- Dynamic Risk State & Traffic Snapshots
CREATE TABLE port_risk_snapshots (
    snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    unlocode VARCHAR(5) REFERENCES ports(unlocode),
    vessel_class_id VARCHAR(20) REFERENCES vessel_classes(class_id),
    grounding_risk_level VARCHAR(10) CHECK (grounding_risk_level IN ('LOW', 'MEDIUM', 'HIGH')),
    anchored_vessel_count INT DEFAULT 0,
    underway_vessel_count INT DEFAULT 0,
    total_active_geofence_count INT DEFAULT 0,
    historical_avg_queue DECIMAL(5, 2) DEFAULT 0.0,
    queue_variance_pct DECIMAL(5, 2) DEFAULT 0.0,
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

*This specification serves as the master architecture plan (`plan-v8.md`) with explicit, step-by-step documentation for the Automated Alternative Port Recommendation Engine and a direct UI display model.*
