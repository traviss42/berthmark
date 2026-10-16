# Port-Call Risk Tracking & Assessment Tool - MVP Project Plan

## 1. Executive Summary

The Port-Call Risk Tracking & Assessment Tool is an interactive application designed to monitor, analyze, and alert stakeholders about operational disruptions, bottlenecks, and safety risks at key ports globally. The Minimum Viable Product (MVP) provides a flexible, multi-tenant framework allowing users to dynamically search, select, add, and monitor ports worldwide with private, custom configurations.

## 2. Target Users

* **Cargo Owners & Shippers:** To track potential cargo delays and proactively manage supply chain buffers.
* **Ocean Carriers & Shipping Lines:** To monitor port bottlenecks and optimize vessel schedules dynamically.
* **Freight Forwarders & Maritime Agents:** To maintain visibility over port operations and coordinate hinterland logistics efficiently.

## 3. Core Risk Architecture & Scoring Logic

The application evaluates port-call risk across four distinct categories using a combination of dynamic statistical baselines and hard safety standards.

### 3.1 Sub-Risk Categories

1. **Congestion Risk:** Measured via active anchorage queue counts, waiting times, and total capacity pressure relative to historical trends.
2. **Terminal Delays:** Evaluated using berth turnaround times, berth-to-anchorage wait ratios, and dwell time anomalies.
3. **Weather Delays:** Tracked using real-time marine weather metrics (wind speed, wave height, swell period, visibility).
4. **Navigational Risk:** Evaluated by cross-referencing environmental constraints against channel/pilotage limits, air draft, and under-keel clearance constraints.

### 3.2 Tiering & Scoring Model

* **Granular Tiers:** Each category is evaluated into three discrete tiers: **Low**, **Medium**, or **High**.
* **Composite Score Logic:** The overall port risk status uses a **Maximum Severity ("Weakest-Link") Rule**. If any single sub-category reaches **High** (e.g., severe weather exceeding safety limits), the top-level composite status for that vessel class immediately jumps to **High**.

## 4. Vessel Taxonomy, Baselines, & Safety Rules

To ensure operational accuracy across different sectors, risk metrics are segmented using a comprehensive global vessel taxonomy derived from raw **AIS Static Data (Message 5: Type Code + Physical Dimensions)**.

### 4.1 Comprehensive Global Vessel Taxonomy

| Sector | Class Category | Dimension & Draft Criteria | Operational & Risk Significance |
| :--- | :--- | :--- | :--- |
| **Containerized Cargo** | **Feeder** | Length $< 150\text{m}$, Beam $< 25\text{m}$, Draft $< 9\text{m}$ | Rapid turnarounds, high maneuverability, minimal windage. |
| | **Panamax / Sub-Panamax** | Length $150\text{--}290\text{m}$, Beam $\le 32.2\text{m}$, Draft $\le 12\text{m}$ | Traditional inter-regional trade routes; legacy lock limits. |
| | **Neo-Panamax** | Length up to $366\text{m}$, Beam $32.2\text{--}51.2\text{m}$, Draft $\le 15.2\text{m}$ | High capacity; expanded canal constraint rules. |
| | **ULCV** (Ultra Large) | Length $> 366\text{m}$, Beam $> 51.2\text{m}$, Draft $> 15\text{m}$ | Severe wind sailage impact; channel squat & strict depth limits. |
| **Liquid Bulk / Tankers** | **MR / Handysize Tanker** | DWT $25,000\text{--}50,000$, Draft $< 11\text{m}$ | Regional product/chemical distribution. |
| | **Aframax** | DWT $80,000\text{--}120,000$, Draft $12\text{--}15\text{m}$ | Medium-depth crude routes and lightering ops. |
| | **Suezmax** | DWT $120,000\text{--}200,000$, Draft up to $16\text{m}$ | Constrained by canal draft & deep-water channels. |
| | **VLCC / ULCC** | DWT $200,000+$, Draft $> 20\text{m}$ | Deep-draft offshore SPM or deep terminal restrictions. |
| **Dry Bulk** | **Handysize / Supramax** | DWT $10,000\text{--}60,000$, Draft $9\text{--}11\text{m}$ | Self-sustaining (geared cranes); accesses smaller ports. |
| | **Panamax (Bulk)** | Beam $\le 32.2\text{m}$, Draft $\le 15\text{m}$ | Major agricultural & coal route standard. |
| | **Capesize** | DWT $120,000+$, Draft $> 17\text{m}$ | Deep-water mineral export/import terminals only. |
| **Specialized** | **PCC / PCTC** (Car Carriers)| High air draft ($> 40\text{m}$), High sailage | Extremely sensitive to lateral crosswinds; strict wind holds. |
| | **LNG / LPG Carriers** | Specialized containment profile | Mandatory safety exclusion zones & tug escorts. |

### 4.2 Baseline & Standard Definitions

* **Dynamic Statistical Baselines:** Congestion and terminal delay metrics are compared against a **rolling 30-day average calculated per vessel class** at each specific port to flag statistical anomalies.
* **Static Operational Safety Standards:** Weather and navigational limits adopt **PIANC Guidelines (Report 121)** as hard safety floors (e.g., wind cutoffs for high-sailage PCTC/ULCV classes, under-keel clearance limits for Capesize/VLCC classes).

## 5. Primary Data Inputs & Sources

* **Vessel Tracking (AIS):** AISStream.io (WebSocket feed for real-time vessel positions, speeds, and metadata within active port bounding zones).
* **Weather & Sea State:** Open-Meteo Marine API / NOAA (free meteorological and oceanographic forecasts globally).
* **Port Reference Data:** UN/LOCODE and World Port Index (WPI) datasets for standard port lookup, names, and base coordinates.
* **Geospatial Boundaries:** Default implementation uses configurable radius geofences (e.g., 5–10 nautical miles) centered on port coordinates, with deduplicated background AIS ingestion across overlapping user requests.

## 6. Scope & Multi-Tenant Port Privacy

* **Global Default Ports:** Major maritime hubs (e.g., Rotterdam, Singapore, Shanghai) provided publicly with pre-configured baselines and geofences.
* **Private User Ports:** Users can search and monitor any port globally using UN/LOCODE. Custom ports, geofence radius settings, and tracking rules remain strictly **private to the user account** that added them.

## 7. Execution Cycle & Notification Model

* **Evaluation Cycle:** The pipeline ingests live data feeds and re-evaluates risk scores on a **6-hour execution loop**.
* **Cooldown Logic:** Anti-flapping rules require sustained score shifts or explicit cooldown windows to prevent alert fatigue.
* **Notification Channels:**
  * **State-Change Email Alerts:** Triggered when a port switches risk tiers (e.g., Medium to High).
  * **Daily Email Digest:** A consolidated summary of all monitored ports sent once daily.
  * **In-App Notifications & Badges:** Real-time visual alerts and warning flags inside the dashboard navigation.