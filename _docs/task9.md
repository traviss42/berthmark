# Task #9 Specification: PIANC Grounding Risk Calculation Module

## Goal
Enhance the PIANC Grounding Risk Calculation Engine to incorporate dynamic tide offset ingestion and calm inner-channel net clearance tiers, preventing false critical grounding alerts for vessels with adequate water clearance (e.g. Neopanamax at Port of LA).

## Tide Offset Retrieval & Integration Strategy
- Data Source & Endpoint: Asynchronous ingestion client (extending Task #8 Weather Client) querying the Open-Meteo Marine API or NOAA CO-OPS REST API for US ports using port coordinates (latitude, longitude).
- Parameters Fetched: Real-time and 24-hour forecast sea level height above MLLW (Mean Lower Low Water) in meters (`tide_height_m`).
- Fallback Handling: If the live tide API endpoint is offline or returns null, default `Dynamic Tide Offset = 0.0m` (conservative static MLLW baseline) and set `tide_data_available = False`.
- Depth Formula: `Available Depth = WPI Channel Depth + Dynamic Tide Offset`.

## Acceptance Criteria
- [ ] Ingest live tide level (meters above MLLW) from Open-Meteo Marine / NOAA API for target port coordinates.
- [ ] Evaluate available water depth as: Available Depth = WPI Channel Depth + Dynamic Tide Offset.
- [ ] Outer / Swell Hazard Rule: When wave swell Hs > 2.0m, evaluate required depth as h_req = 1.30 * Vessel Draft.
- [ ] Standard Gross Multiplier: When wave swell Hs <= 2.0m, evaluate required depth as h_req = 1.10 * Vessel Draft.
- [ ] Calm Inner Channel Net Tier: When wave swell Hs <= 1.0m, evaluate net clearance margin as Net Margin = Available Depth - Vessel Draft.
- [ ] Risk Categorization Rules:
      - LOW RISK: Available Depth >= h_req + 1.0m (safe clearance margin).
      - MEDIUM RISK (Tidal Window Required): Available Depth at low tide (0.0m offset) < h_req, but Available Depth at high tide >= h_req OR Net Margin >= 0.9m under calm swell (Hs <= 1.0m).
      - HIGH / CRITICAL RISK: Available Depth at high tide < h_req AND Net Margin < 0.9m (grounding hazard).
- [ ] Unit Tests: Add unit tests for Port of LA (WPI channel depth 16.1m) and Neopanamax vessel class (draft 15.2m):
      - Test 1 (Static Low Tide / 0.0m Offset): Assert 16.1m available depth evaluates to MEDIUM RISK (Tidal Window Required) instead of CRITICAL GROUNDING HAZARD.
      - Test 2 (Dynamic High Tide / +1.2m Offset): Assert 17.3m available depth evaluates to LOW RISK.
      - Test 3 (API Fallback): Assert offline tide API defaults to 0.0m offset with tide_data_available = False.

## Out of Scope
- Real-time bathymetric sonar updates or custom multi-polygon GIS berth geometries (continue using WPI controlling depths).

## Constraints
- Keep calculation logic inside backend services (e.g., `backend/app/services/grounding_risk.py`).
- Maintain compatibility with the OpenAPI `RiskAssessment` schema.
- Strict Workspace Boundary: Only read and modify files strictly inside this repository root (`./`).
