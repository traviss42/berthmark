"""End-to-End User Journey Integration Verification Test Suite (Issue 24).

Validates the complete 5-step user lifecycle non-interactively:
1. Authentication & profile verification (valid login, invalid login edge cases).
2. Port directory search & empty bounds.
3. Multi-vessel port subscriptions & constraint enforcement (multi-class, duplicate 409).
4. Differential vessel class risk calculation & direct diversion recommendations.
5. Alert logs, live notification lifecycle & system default deletion prevention.
"""

from datetime import datetime, timezone
import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.auth.seed import (
    DEFAULT_OPERATOR_EMAIL,
    DEFAULT_OPERATOR_PASSWORD,
    seed_default_user,
)
from backend.database import get_db_session
from backend.main import app
from backend.models import AlertLog, Base, Port, PortRiskSnapshot, User, UserWatchlist
from backend.ports.service import BENCHMARK_PORTS_METADATA
from backend.schemas.notification import NotificationCreate
from backend.services.grounding import calculate_grounding_risk
from backend.services.recommendation import (
    calculate_haversine_distance_nm,
    recommend_alternative_ports,
)
from backend.taxonomy.seed import seed_vessel_classes


@pytest_asyncio.fixture
async def e2e_test_db():
    """Provision in-memory SQLite database seeded with vessel taxonomy, benchmark ports, and default user."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        # 1. Seed vessel classes
        await seed_vessel_classes(session)

        # 2. Seed default user
        default_user = await seed_default_user(session)

        # 3. Seed benchmark ports and regional candidate ports
        ports = [
            Port(
                unlocode="NLRTM",
                port_name="Port of Rotterdam",
                country_code="NL",
                subdivision_code="NL-ZH",
                latitude=51.9244,
                longitude=4.4777,
                channel_depth_m=16.5,
                is_depth_available=True,
                reconciliation_method="EXACT_UNLOCODE",
            ),
            Port(
                unlocode="SGSIN",
                port_name="Port of Singapore",
                country_code="SG",
                subdivision_code="SG",
                latitude=1.2648,
                longitude=103.8408,
                channel_depth_m=15.0,
                is_depth_available=True,
                reconciliation_method="EXACT_UNLOCODE",
            ),
            Port(
                unlocode="USHOU",
                port_name="Port of Houston",
                country_code="US",
                subdivision_code="US-TX",
                latitude=29.75,
                longitude=-95.28,
                channel_depth_m=14.0,
                is_depth_available=True,
                reconciliation_method="EXACT_UNLOCODE",
            ),
            Port(
                unlocode="BEANR",
                port_name="Port of Antwerp-Bruges",
                country_code="BE",
                subdivision_code="BE-VAN",
                latitude=51.22,
                longitude=4.40,
                channel_depth_m=15.0,
                is_depth_available=True,
                reconciliation_method="EXACT_UNLOCODE",
            ),
            Port(
                unlocode="CNSHA",
                port_name="Port of Shanghai",
                country_code="CN",
                subdivision_code="CN-SH",
                latitude=31.23,
                longitude=121.47,
                channel_depth_m=16.0,
                is_depth_available=True,
                reconciliation_method="EXACT_UNLOCODE",
            ),
            # Wilhelmshaven alternative port candidate in regional jurisdiction (deep water 20.0m)
            Port(
                unlocode="DEWVN",
                port_name="Port of Wilhelmshaven",
                country_code="DE",
                subdivision_code="NL-ZH",
                latitude=53.53,
                longitude=8.14,
                channel_depth_m=20.0,
                is_depth_available=True,
                reconciliation_method="EXACT_UNLOCODE",
            ),
            # Port with depth unavailable
            Port(
                unlocode="NODEP",
                port_name="Port Without Depth",
                country_code="NL",
                subdivision_code="NL-ZH",
                latitude=52.00,
                longitude=4.30,
                channel_depth_m=None,
                is_depth_available=False,
                reconciliation_method="EXACT_UNLOCODE",
            ),
        ]
        session.add_all(ports)
        await session.commit()

        # Seed low-risk snapshot for Wilhelmshaven candidate
        snap = PortRiskSnapshot(
            snapshot_id=uuid.uuid4(),
            unlocode="DEWVN",
            vessel_class_id="neoPanamax",
            overall_risk_level="LOW",
            congestion_risk_level="LOW",
            weather_risk_level="LOW",
            grounding_risk_level="LOW",
            anchored_vessel_count=3,
            underway_vessel_count=2,
            total_active_geofence_count=5,
            historical_avg_queue=3.0,
            queue_variance_pct=0.0,
            swell_height_m=1.0,
            wind_speed_kts=12.0,
            updated_at=datetime.now(timezone.utc),
        )
        session.add(snap)
        await session.commit()

        user_id = default_user.id

    yield session_factory, user_id
    await engine.dispose()


# ─── 1. End-to-End User Journey Verification ─────────────────────────────────

@pytest.mark.asyncio
async def test_end_to_end_user_journey(e2e_test_db):
    """Execute complete 5-step user journey non-interactively verifying contract compliance."""
    session_factory, user_id = e2e_test_db

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = override_get_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # ─────────────────────────────────────────────────────────────────
            # STEP 1: Authentication & User Profile
            # ─────────────────────────────────────────────────────────────────
            # 1a. Successful Login with default operator credentials
            login_payload = {
                "email": DEFAULT_OPERATOR_EMAIL,
                "password": DEFAULT_OPERATOR_PASSWORD,
            }
            res_login = await client.post("/api/v1/auth/login", json=login_payload)
            assert res_login.status_code == 200, res_login.text
            login_data = res_login.json()

            assert "accessToken" in login_data
            assert login_data["tokenType"] == "Bearer"
            assert login_data["expiresIn"] > 0
            assert login_data["user"]["email"] == DEFAULT_OPERATOR_EMAIL
            assert login_data["user"]["name"] == "Ship Operations Manager"

            token = login_data["accessToken"]
            auth_headers = {"Authorization": f"Bearer {token}"}

            # 1b. Verify current authenticated user profile via GET /api/v1/auth/me
            res_me = await client.get("/api/v1/auth/me", headers=auth_headers)
            assert res_me.status_code == 200
            me_data = res_me.json()
            assert me_data["id"] == str(user_id)
            assert me_data["email"] == DEFAULT_OPERATOR_EMAIL
            assert me_data["name"] == "Ship Operations Manager"
            assert "createdAt" in me_data

            # 1c. Authentication edge case: Invalid credentials returns HTTP 401 ErrorResponse
            bad_login = await client.post(
                "/api/v1/auth/login",
                json={"email": DEFAULT_OPERATOR_EMAIL, "password": "WrongPassword999!"},
            )
            assert bad_login.status_code == 401
            bad_data = bad_login.json()
            assert bad_data["error"] == "Unauthorized"
            assert bad_data["statusCode"] == 401
            assert "Invalid credentials" in bad_data["message"]

            # ─────────────────────────────────────────────────────────────────
            # STEP 2: Port Directory Search & Boundaries
            # ─────────────────────────────────────────────────────────────────
            # 2a. Query search directory for Rotterdam
            res_search = await client.get("/api/v1/ports/search?q=Rotterdam", headers=auth_headers)
            assert res_search.status_code == 200
            search_results = res_search.json()
            assert len(search_results) >= 1
            rtm = next(p for p in search_results if p["locode"] == "NLRTM")
            assert rtm["name"] == "Port of Rotterdam"
            assert rtm["lat"] == 51.9244
            assert rtm["lon"] == 4.4777

            # 2b. Boundary: Unknown query returns HTTP 200 with empty list []
            res_empty_search = await client.get("/api/v1/ports/search?q=UNKNOWN_PORT_XYZ", headers=auth_headers)
            assert res_empty_search.status_code == 200
            assert res_empty_search.json() == []

            # ─────────────────────────────────────────────────────────────────
            # STEP 3: Multi-Vessel Subscriptions & Constraint Enforcement
            # ─────────────────────────────────────────────────────────────────
            # 3a. Initial state: authenticated user has only the 5 default benchmark ports
            initial_ports_res = await client.get("/api/v1/ports", headers=auth_headers)
            assert initial_ports_res.status_code == 200
            initial_ports = initial_ports_res.json()
            assert len(initial_ports) == 5
            for p in initial_ports:
                assert p["isDefault"] is True

            # 3b. Port subscription #1: Rotterdam under VLCC
            res_sub1 = await client.post(
                "/api/v1/ports",
                json={
                    "name": "Port of Rotterdam",
                    "locode": "NLRTM",
                    "country": "Netherlands",
                    "lat": 51.9244,
                    "lon": 4.4777,
                    "geofenceRadiusNm": 12.0,
                    "vesselClass": "vlcc",
                },
                headers=auth_headers,
            )
            assert res_sub1.status_code == 201
            sub1_data = res_sub1.json()
            assert sub1_data["locode"] == "NLRTM"
            assert sub1_data["vesselClass"] == "vlcc"
            assert sub1_data["addedByUserId"] == str(user_id)

            # 3c. Port subscription #2: Singapore under neoPanamax
            res_sub2 = await client.post(
                "/api/v1/ports",
                json={
                    "name": "Port of Singapore",
                    "locode": "SGSIN",
                    "country": "Singapore",
                    "lat": 1.2648,
                    "lon": 103.8408,
                    "geofenceRadiusNm": 10.0,
                    "vesselClass": "neoPanamax",
                },
                headers=auth_headers,
            )
            assert res_sub2.status_code == 201
            assert res_sub2.json()["vesselClass"] == "neoPanamax"

            # 3d. Port subscription #3: Houston under aframax
            res_sub3 = await client.post(
                "/api/v1/ports",
                json={
                    "name": "Port of Houston",
                    "locode": "USHOU",
                    "country": "United States",
                    "lat": 29.75,
                    "lon": -95.28,
                    "geofenceRadiusNm": 10.0,
                    "vesselClass": "aframax",
                },
                headers=auth_headers,
            )
            assert res_sub3.status_code == 201
            assert res_sub3.json()["vesselClass"] == "aframax"

            # 3e. Multi-class subscription: Rotterdam a second time under handysize
            res_sub_handy = await client.post(
                "/api/v1/ports",
                json={
                    "name": "Port of Rotterdam",
                    "locode": "NLRTM",
                    "country": "Netherlands",
                    "lat": 51.9244,
                    "lon": 4.4777,
                    "geofenceRadiusNm": 8.0,
                    "vesselClass": "handysize",
                },
                headers=auth_headers,
            )
            assert res_sub_handy.status_code == 201
            assert res_sub_handy.json()["vesselClass"] == "handysize"

            # 3f. Duplicate subscription edge case: Rotterdam under VLCC again -> 409 Conflict
            res_sub_dup = await client.post(
                "/api/v1/ports",
                json={
                    "name": "Port of Rotterdam",
                    "locode": "NLRTM",
                    "country": "Netherlands",
                    "lat": 51.9244,
                    "lon": 4.4777,
                    "vesselClass": "vlcc",
                },
                headers=auth_headers,
            )
            assert res_sub_dup.status_code == 409
            dup_data = res_sub_dup.json()
            assert dup_data["error"] == "Conflict"
            assert dup_data["statusCode"] == 409
            assert "already in your watchlist" in dup_data["message"]

            # 3g. Monitored list contains 5 defaults + 4 subscriptions = 9 entries
            res_all_monitored = await client.get("/api/v1/ports", headers=auth_headers)
            assert res_all_monitored.status_code == 200
            all_monitored = res_all_monitored.json()
            assert len(all_monitored) == 9

            rtm_subscriptions = [p for p in all_monitored if p["locode"] == "NLRTM" and not p["isDefault"]]
            assert len(rtm_subscriptions) == 2
            vclasses = {p["vesselClass"] for p in rtm_subscriptions}
            assert vclasses == {"vlcc", "handysize"}

            # ─────────────────────────────────────────────────────────────────
            # STEP 4: Differential Class Risk Calculation & Diversion Recommendations
            # ─────────────────────────────────────────────────────────────────
            # 4a. Grounding risk for Rotterdam channel (16.5m depth) under heavy swell Hs=2.8m
            # For VLCC: Draft = 21.0m. Swell multiplier 1.35 -> h_req = 28.35m.
            # Channel depth 16.5m < 28.35m -> UKC margin = -11.85m -> HIGH RISK (Score 90.0)
            vlcc_risk = calculate_grounding_risk(
                vessel_class="vlcc",
                channel_depth_m=16.5,
                wave_height_m=2.8,
            )
            assert vlcc_risk.tier == "high"
            assert vlcc_risk.score == 90.0
            assert vlcc_risk.ukc_margin_m is not None and vlcc_risk.ukc_margin_m < 0.0
            assert vlcc_risk.required_depth_m == 28.35

            # For Handymax/Handysize: Draft = 10.5m. Swell multiplier 1.35 -> h_req = 14.18m.
            # Channel depth 16.5m - 14.18m = +2.32m >= 1.0m -> LOW RISK (Score 25.0)
            handy_risk = calculate_grounding_risk(
                vessel_class="handysize",
                channel_depth_m=16.5,
                wave_height_m=2.8,
            )
            assert handy_risk.tier == "low"
            assert handy_risk.score == 25.0
            assert handy_risk.ukc_margin_m is not None and handy_risk.ukc_margin_m >= 1.0
            assert handy_risk.required_depth_m == 14.18

            # 4b. Missing depth edge case: Port with is_depth_available = False
            missing_depth_risk = calculate_grounding_risk(
                vessel_class="vlcc",
                channel_depth_m=None,
                wave_height_m=2.8,
                is_depth_available=False,
            )
            assert missing_depth_risk.tier == "low"
            assert missing_depth_risk.score == 25.0
            assert missing_depth_risk.is_depth_available is False
            assert "Controlling depth data not available" in missing_depth_risk.detail

            # 4c. Alternative port diversion recommendations
            async with session_factory() as session:
                rotterdam_port = (await session.execute(
                    select(Port).where(Port.unlocode == "NLRTM")
                )).scalar_one()

                # High-risk Neo-Panamax (draft 15.2m * 1.1 = 16.72m required depth)
                # Wilhelmshaven (DEWVN) channel depth 20.0m >= 16.72m and LOW risk -> recommended!
                recs = await recommend_alternative_ports(
                    session=session,
                    primary_port=rotterdam_port,
                    vessel_class="neoPanamax",
                    primary_risk_tier="HIGH",
                    wave_height_m=1.0,
                )
                assert len(recs) >= 1
                wvn_rec = next((r for r in recs if r.unlocode == "DEWVN"), None)
                assert wvn_rec is not None
                assert wvn_rec.portName == "Port of Wilhelmshaven"
                assert wvn_rec.riskTier == "low"
                assert wvn_rec.channelDepthM == 20.0
                assert wvn_rec.distanceNm > 0.0

                # Top-3 distance ordering check
                distances = [r.distanceNm for r in recs]
                assert distances == sorted(distances)

                # Edge case: No qualifying alternatives when required depth exceeds all candidates
                recs_empty = await recommend_alternative_ports(
                    session=session,
                    primary_port=rotterdam_port,
                    vessel_class="vlcc",
                    primary_risk_tier="HIGH",
                    wave_height_m=2.8,  # requires 28.35m > 20.0m max candidate depth
                )
                assert recs_empty == []

            # ─────────────────────────────────────────────────────────────────
            # STEP 5: Alert Logs, Live Notification Lifecycle & System Deletion Edge Cases
            # ─────────────────────────────────────────────────────────────────
            # 5a. Dispatch a risk state-change notification via POST /api/v1/notifications
            notif_create_payload = {
                "type": "stateChange",
                "portId": "port-rotterdam",
                "portName": "Port of Rotterdam",
                "previousTier": "low",
                "newTier": "high",
            }
            res_notif = await client.post(
                "/api/v1/notifications",
                json=notif_create_payload,
                headers=auth_headers,
            )
            assert res_notif.status_code == 201
            notif_data = res_notif.json()
            notif_id = notif_data["id"]
            assert notif_data["portId"] == "port-rotterdam"
            assert notif_data["tier"] == "high"
            assert notif_data["previousTier"] == "low"
            assert notif_data["read"] is False

            # 5b. Notification feed & bell badge counter
            res_list_notif = await client.get("/api/v1/notifications", headers=auth_headers)
            assert res_list_notif.status_code == 200
            notifs = res_list_notif.json()
            assert len(notifs) >= 1
            assert any(n["id"] == notif_id and not n["read"] for n in notifs)

            # Query unread only
            res_unread = await client.get("/api/v1/notifications?unreadOnly=true", headers=auth_headers)
            assert res_unread.status_code == 200
            assert len(res_unread.json()) >= 1

            # 5c. Mark notification as read
            res_read = await client.patch(f"/api/v1/notifications/{notif_id}/read", headers=auth_headers)
            assert res_read.status_code == 200
            assert res_read.json()["read"] is True

            # Subsequent unread query confirms bell counter decremented to 0
            res_unread_after = await client.get("/api/v1/notifications?unreadOnly=true", headers=auth_headers)
            assert res_unread_after.status_code == 200
            assert len(res_unread_after.json()) == 0

            # 5d. System default port deletion edge case: Attempting to delete default port -> 400 Bad Request
            for default_target in ["port-rotterdam", "NLRTM"]:
                res_del_default = await client.delete(f"/api/v1/ports/{default_target}", headers=auth_headers)
                assert res_del_default.status_code == 400
                del_err = res_del_default.json()
                assert del_err["error"] == "Bad Request"
                assert del_err["statusCode"] == 400
                assert "System default ports cannot be removed." in del_err["message"]

            # 5e. Clean up custom subscription via DELETE
            res_del_custom = await client.delete(f"/api/v1/ports/{sub1_data['id']}", headers=auth_headers)
            assert res_del_custom.status_code == 204

    finally:
        app.dependency_overrides.clear()
