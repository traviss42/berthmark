#!/usr/bin/env python3
"""Diagnostic script to verify live connectivity and authentication with all external APIs."""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Add backend to PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import websockets
from app.clients.unlocode_db import UnlocodeDatabase
from app.config import get_settings


GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


async def test_unlocode():
    print(f"\n{BOLD}1. UN/LOCODE Maritime Database (SQLite){RESET}")
    print("   --------------------------------------")
    t0 = time.time()
    try:
        db = UnlocodeDatabase()
        count = db.count_ports()
        search_res = db.search_ports("Rotterdam")
        elapsed = round((time.time() - t0) * 1000, 1)

        if count >= 40 and len(search_res) > 0:
            print(f"   {GREEN}✔ CONNECTED & HEALTHY{RESET} ({elapsed} ms)")
            print(f"     • Total indexed ports: {count}")
            print(f"     • Sample lookup ('Rotterdam'): {search_res[0].name} [{search_res[0].locode}]")
            return True
        else:
            print(f"   {YELLOW}⚠ WARNING:{RESET} database exists but unexpected count ({count})")
            return False
    except Exception as e:
        print(f"   {RED}✘ FAILED:{RESET} {str(e)}")
        return False


async def test_weather():
    print(f"\n{BOLD}2. Marine & Atmospheric Weather API (Open-Meteo){RESET}")
    print("   ---------------------------------------------")
    t0 = time.time()
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": 51.9244,
            "longitude": 4.4777,
            "current": "wind_speed_10m,wind_gusts_10m",
            "wind_speed_unit": "kn",
        }
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, params=params)
            elapsed = round((time.time() - t0) * 1000, 1)

            if resp.status_code == 200:
                data = resp.json().get("current", {})
                wind = data.get("wind_speed_10m")
                gust = data.get("wind_gusts_10m")
                print(f"   {GREEN}✔ CONNECTED & HEALTHY{RESET} ({elapsed} ms)")
                print(f"     • Endpoint: {url}")
                print(f"     • Live wind at Port of Rotterdam: {wind} knots (gusts: {gust} knots)")
                return True
            else:
                print(f"   {RED}✘ FAILED:{RESET} Status {resp.status_code}")
                return False
    except Exception as e:
        print(f"   {RED}✘ FAILED:{RESET} {str(e)}")
        return False


async def test_aisstream():
    print(f"\n{BOLD}3. AISStream Live Vessel Traffic (WebSocket API){RESET}")
    print("   ---------------------------------------------")
    settings = get_settings()
    api_key = settings.AISSTREAM_API_KEY.strip()

    if not api_key:
        print(f"   {YELLOW}⚠ UNCONFIGURED:{RESET} AISSTREAM_API_KEY is not set in backend/.env")
        print("     • Add AISSTREAM_API_KEY=<your-key> to backend/.env to enable live vessel streaming.")
        return False

    masked_key = f"{api_key[:6]}...{api_key[-4:]}"
    print(f"     • API Key loaded: {masked_key} (length: {len(api_key)})")

    t0 = time.time()
    ws_url = "wss://stream.aisstream.io/v0/stream"
    try:
        async with websockets.connect(ws_url, close_timeout=3.0, ping_timeout=5.0) as ws:
            # Subscribe to Rotterdam Port geofence
            sub = {
                "APIKey": api_key,
                "BoundingBoxes": [
                    [[51.8, 3.8], [52.1, 4.6]]
                ],
                "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
            }
            await ws.send(json.dumps(sub))

            confirmation_received = False
            ships_detected = 0
            start = asyncio.get_event_loop().time()

            while asyncio.get_event_loop().time() - start < 4.0:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    msg = json.loads(raw)
                    m_type = msg.get("MessageType")
                    if m_type == "SubscriptionConfirmation":
                        confirmation_received = True
                    elif m_type in ("PositionReport", "ShipStaticData"):
                        ships_detected += 1
                except asyncio.TimeoutError:
                    break

            elapsed = round((time.time() - t0) * 1000, 1)

            if confirmation_received:
                print(f"   {GREEN}✔ AUTHENTICATED & STREAMING{RESET} ({elapsed} ms)")
                print(f"     • Endpoint: {ws_url}")
                print(f"     • Subscription confirmation: Accepted")
                print(f"     • Real-time vessels sampled in Rotterdam geofence: {ships_detected}")
                return True
            else:
                print(f"   {YELLOW}⚠ CONNECTED BUT NO CONFIRMATION RECEIVED{RESET} ({elapsed} ms)")
                return False
    except Exception as e:
        print(f"   {RED}✘ FAILED:{RESET} {str(e)}")
        return False


async def main():
    print(f"\n{BOLD}{CYAN}===================================================={RESET}")
    print(f"{BOLD}{CYAN}    Berthmark - External APIs Diagnostic Suite     {RESET}")
    print(f"{BOLD}{CYAN}===================================================={RESET}")

    r1 = await test_unlocode()
    r2 = await test_weather()
    r3 = await test_aisstream()

    print(f"\n{BOLD}Summary:{RESET}")
    print(f"  • UN/LOCODE Database:  {'[PASS]' if r1 else '[FAIL]'}")
    print(f"  • Open-Meteo Weather:  {'[PASS]' if r2 else '[FAIL]'}")
    print(f"  • AISStream WebSocket: {'[PASS]' if r3 else '[FAIL]'}")

    if r1 and r2 and r3:
        print(f"\n{GREEN}{BOLD}All external APIs and datasets are online, authenticated, and functioning properly!{RESET}\n")
        return 0
    else:
        print(f"\n{YELLOW}{BOLD}Some APIs reported issues or are not yet configured.{RESET}\n")
        return 1


if __name__ == "__main__":
    code = asyncio.run(main())
    sys.exit(code)
