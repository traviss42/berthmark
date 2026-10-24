# Task Backlog

## 1. Empty Backend Project Setup with Passing Test
Goal: Initialize the backend Python project with dependency management and a passing smoke test.
Description: Set up the backend project structure using `pyproject.toml` and `uv` with FastAPI, Uvicorn, and Pytest. Create an initial health-check endpoint and test file ensuring `uv run pytest` executes cleanly. This provides the foundation for subsequent API and service implementations.

## 2. Database Schema and Connection Setup
Goal: Create the SQLite database structure and table schemas defined in the architecture plan.
Description: Define database tables for ports, vessel classes, user watchlists, port traffic baselines, port risk snapshots, and alert logs using an ORM or migration script. Implement a database connection manager that provisions tables and enforces foreign key constraints. Write unit tests confirming successful schema initialization and table creation.

## 3. UN/LOCODE and WPI Data Ingestion Pipeline
Goal: Build and test an ingestion script that reconciles UN/LOCODE CSV files with NGA World Port Index data.
Description: Implement an ETL script to parse UN/LOCODE location CSVs (`data/unlocode/`) and NGA World Port Index records (`data/wpi/UpdatedPub150.csv`). Join datasets on 5-character LOCODEs with fallback fuzzy-distance matching, populating the ports database table with coordinates, depths, and quality flags. Write automated tests asserting accurate data loading for benchmark ports like Rotterdam and Singapore.

## 4. Vessel Benchmark Taxonomy API
Goal: Seed the 13 benchmark vessel classes and implement the vessel taxonomy endpoint.
Description: Seed the database with the 13 commercial vessel classes across containerized, liquid bulk, dry bulk, and specialized sectors alongside their draft, beam, and LOA dimensions. Implement the `GET /api/v1/vessel-classes` endpoint adhering to the OpenAPI specification schemas. Add unit tests asserting complete category retrieval and correct field validation.

## 5. User Authentication and Profile Endpoints
Goal: Implement user authentication with password hashing and JWT token issuance.
Description: Build user credential verification and authentication routes including `POST /api/v1/auth/login` to return signed JWT access tokens. Implement the `GET /api/v1/auth/me` endpoint secured by Bearer token authorization to return the authenticated user profile. Write tests validating successful logins, token expiration, and unauthorized access rejections.

## 6. Port Directory Search and Lookup Endpoints
Goal: Implement port search and retrieval endpoints matching the OpenAPI specification.
Description: Implement `GET /api/v1/ports/default` to return system benchmark ports, `GET /api/v1/ports/search` to support full-text search across port names, LOCODEs, and countries, and `GET /api/v1/ports/{portId}` for single-port lookups. Ensure response payloads conform to the OpenAPI `Port` schema. Write integration tests covering case-insensitive search queries and 404 responses for missing ports.

## 7. User Watchlist Management API
Goal: Implement endpoints for adding, listing, and removing custom monitored ports in user watchlists.
Description: Implement `GET /api/v1/ports` to return a user's combined default and custom monitored ports, `POST /api/v1/ports` to add custom ports with specified geofence radii, and `DELETE /api/v1/ports/{portId}` to remove user-added ports. Enforce authorization rules prohibiting deletion of system default ports or other users' custom ports. Add tests verifying per-user watchlist isolation, conflict responses on duplicates, and successful removals.

## 8. Open-Meteo Weather Ingestion Client
Goal: Build an asynchronous HTTP client to fetch real-time marine weather and swell data from Open-Meteo.
Description: Implement a client service that queries Open-Meteo Marine and Weather APIs for significant wave height, wave period, wind speed, gusts, and visibility by port coordinates. Structure the fetched metrics into the `WeatherMetrics` schema format with in-memory caching to prevent excessive API calls. Write unit tests with mocked API responses verifying parsing precision and graceful fallback on network timeouts.

## 9. PIANC Grounding Risk Calculation Module
Goal: Implement the Under-Keel Clearance and grounding depth risk calculation engine.
Description: Create a calculation service implementing PIANC Report 121 Under-Keel Clearance formulas against controlling channel depths under calm and swell ($H_s > 2.0\text{ m}$) conditions. Output LOW, MEDIUM, or HIGH grounding risk tiers alongside under-keel clearance margin values for any assigned vessel class. Include comprehensive unit tests covering diverse vessel drafts and varying sea swell heights.

## 10. Dynamic Point-Offset Bounding Box Generator
Goal: Generate geographic bounding boxes from port coordinates for spatial AIS monitoring.
Description: Implement coordinate utility functions that calculate point-offset bounding box boundaries adjusted for latitude from port coordinates. Format bounding box tuples into the array structure expected by the AISStream WebSocket connection payload. Write unit tests validating bounding box calculations across equatorial, mid-latitude, and high-latitude test coordinates.

## 11. AISStream WebSocket Worker and Traffic Classification Engine
Goal: Ingest real-time AIS position reports and categorize vessels into traffic state sets.
Description: Build a WebSocket client connecting to AISStream.io that subscribes to bounding boxes for ports in active user watchlists across regional connection pools. Ingest `PositionReport` events to classify vessels into stationary ($\text{SOG} \le 0.5\text{ kts}$) and underway ($\text{SOG} > 0.5\text{ kts}$) MMSI sets inside a rolling 15–20 minute in-memory window. Add tests verifying accurate traffic state classification and automatic purging of inactive vessel pings.

## 12. Port Traffic Baselines and Congestion Risk Module
Goal: Calculate historical traffic moving averages, queue variance, and congestion risk tiers.
Description: Create repository methods to persist and retrieve 7-day and 30-day hourly historical traffic moving averages for monitored ports. Implement the congestion risk engine to calculate queue variance percentages ($\Delta Q_{pct}$) against baseline averages and assign LOW, MEDIUM, or HIGH congestion risk tiers. Write unit tests testing boundary conditions for ship counts and variance thresholds.

## 13. Terminal Delay and Navigational Metrics Aggregator
Goal: Calculate terminal turnaround and navigational clearance metrics for port assessments.
Description: Implement analytical calculation services to compute berth turnaround hours, berth-to-anchorage wait ratios, dwell time anomaly scores, and dynamic air draft/tide clearances. Assemble these values alongside congestion and weather metrics into the OpenAPI `PortMetrics` schema structure. Provide unit tests validating metric calculations and payload schema conformity.

## 14. Weakest-Link Overall Risk Engine and Single Assessment API
Goal: Implement the composite risk evaluation engine and the single-port risk endpoint.
Description: Build the composite risk aggregator applying the Weakest-Link rule across congestion, terminal delays, weather, and navigational sub-risks. Implement `GET /api/v1/ports/{portId}/risk` accepting a port identifier and `vesselClass` query parameter to return a complete `RiskAssessment` object. Write tests verifying that any individual HIGH sub-risk escalates the composite tier to HIGH.

## 15. Bulk Risk Assessment Endpoint
Goal: Implement the bulk port risk evaluation endpoint for batch dashboard loading.
Description: Implement `POST /api/v1/risk/assessments/bulk` accepting an array of port IDs and a target vessel class to compute risk assessments concurrently. Return an array of `RiskAssessment` objects matching the OpenAPI schema while optimizing database queries. Add integration tests verifying batch calculations and invalid vessel class rejection.

## 16. Historical Risk Trend Time-Series API
Goal: Implement the historical risk trend endpoint sampling past evaluation cycles.
Description: Create a data store for periodic risk assessment snapshots sampled at 6-hour evaluation cycles. Implement `GET /api/v1/ports/{portId}/risk/history` returning chronological evaluation points capped at 40 points over a user-requested day range. Write tests verifying sampling intervals, day count parameter validation, and chronological ordering.

## 17. Automated Alternative Port Recommendation Engine
Goal: Build the candidate port discovery and ranking pipeline triggered by high-risk ports.
Description: Implement the recommendation algorithm that triggers whenever a port's overall risk reaches HIGH or CRITICAL. Filter candidate ports in the same ISO 3166-2 subdivision by PIANC depth clearance constraints ($WPI_{channel\_de} \ge h_{req}$), rank survivors by Haversine nautical distance, and verify their current weather status. Write unit tests validating that unsuitable shallow ports are excluded and eligible alternatives are ranked by proximity.

## 18. Notification Service and State-Change Alert API
Goal: Implement risk state-change alert generation and notification feed management endpoints.
Description: Build the notification engine that monitors risk transitions during snapshot evaluations and dispatches alerts when risk tiers change. Implement `GET /api/v1/notifications`, `POST /api/v1/notifications`, `PATCH /api/v1/notifications/{id}/read`, and `POST /api/v1/notifications/mark-all-read` in compliance with OpenAPI schemas. Write tests verifying notification creation, unread count filtering, and read status persistence.

## 19. Frontend API Client and Authentication Integration
Goal: Connect the React frontend to the backend REST API and implement user login flow.
Description: Replace frontend mock service adapters with HTTP client implementations targeting backend `/api/v1` routes and managing JWT Bearer tokens. Implement user login state, token persistence in local storage, and profile hydration in the React application. Write tests asserting authenticated HTTP requests, error handling for expired tokens, and redirect behaviors.

## 20. Frontend Dashboard High-Density Card Grid
Goal: Update the dashboard card grid to render all real-time operational metrics directly without drawers.
Description: Refactor dashboard cards to display vessel class headers, color-coded overall risk badges, 4-dimension traffic breakdown counts, weather/depth clearance values, and cold-start indicators ("Initializing Live Traffic..."). Ensure all operational values are displayed directly on the card face without relying on slide-out drawers. Write frontend component tests validating card rendering and risk badge color coding.

## 21. Frontend Inline Alternative Port Diversion Cards
Goal: Render inline alternative port recommendations directly on high-risk dashboard cards.
Description: Integrate alternative port recommendation data into an inline sub-card on dashboard cards whenever overall risk is HIGH or CRITICAL. Display candidate port names, UN/LOCODE, nautical distance, and controlling channel depth margins directly within the card layout. Write component tests verifying that the alternative port section appears only under high risk and renders accurate values.

## 22. Frontend Interactive Map with Direct Popups
Goal: Implement the interactive map view rendering color-coded pins and direct metric popups.
Description: Implement a full-screen interactive map plotting monitored ports at exact coordinates with pins colored by composite risk tier. Display direct map popups on marker click showing traffic breakdown, weather, depth clearance, and alternative recommendations without slide-out drawers. Add component tests ensuring pin rendering and correct popup content display.

## 23. Frontend Notification Bell and Live Alert Feed
Goal: Implement the in-app notification bell with unread badge counter and alert panel.
Description: Integrate a notification bell in the top navigation bar showing an active badge with unread alert counts. Connect the notification dropdown to backend notification endpoints to display risk state-change events and support marking individual or all notifications as read. Write tests verifying badge count updates and read status interactions.

## 24. End-to-End User Journey Integration Verification
Goal: Validate the complete first-run user walkthrough and automated test suite.
Description: Implement automated end-to-end integration tests verifying the first-run journey from authentication and empty watchlist state to adding ports, viewing cold-start and live traffic, triggering alert notifications, and rendering alternative port recommendations. Ensure all backend tests (`uv run pytest`) and frontend tests (`npm --prefix frontend test`) pass cleanly.
