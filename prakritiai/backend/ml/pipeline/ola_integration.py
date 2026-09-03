"""OLA Maps traffic + routing integration with a local simulator fallback."""

import logging
import os
import random
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)

OLA_API_KEY = os.environ.get("OLA_API_KEY", "")
OLA_BASE_URL = os.environ.get("OLA_BASE_URL", "https://api.olamaps.com").rstrip("/")

TRAFFIC_LEVELS = ("low", "moderate", "heavy")
TRAFFIC_DELAY_SECONDS = {"low": 0, "moderate": 180, "heavy": 600}
TRAFFIC_SPEED_KMPH = {"low": 45.0, "moderate": 28.0, "heavy": 12.0}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))





async def get_traffic_aware_route(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
) -> Dict[str, Any]:
    if not OLA_API_KEY:
        raise ValueError("OLA_API_KEY is not set.")

    url = f"{OLA_BASE_URL}/routing/v1/directions"
    params = {
        "origin": f"{origin_lat},{origin_lon}",
        "destination": f"{dest_lat},{dest_lon}",
        "mode": "driving",
        "alternatives": "true",
        "api_key": OLA_API_KEY,
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        routes = _parse_ola_routes(data)
        if not routes:
            raise ValueError("No routes returned from Ola Maps.")
        recommended = min(routes, key=lambda r: r.get("duration_seconds", 10**9))
        return {
            "routes": routes,
            "recommended_route": recommended,
            "source": "ola",
        }
    except Exception as e:
        logger.warning("OLA routing failed: %s", e)
        raise e


def _parse_ola_routes(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_routes = data.get("routes") or data.get("data") or []
    if isinstance(raw_routes, dict):
        raw_routes = [raw_routes]
    parsed: List[Dict[str, Any]] = []
    for i, r in enumerate(raw_routes):
        legs = r.get("legs") or []
        duration = r.get("duration") or r.get("duration_seconds")
        distance = r.get("distance") or r.get("distance_meters")
        if duration is None and legs:
            duration = sum(leg.get("duration", 0) for leg in legs)
        if distance is None and legs:
            distance = sum(leg.get("distance", 0) for leg in legs)
        duration_s = int(duration or 0)
        delay = int(r.get("duration_in_traffic", duration_s) - duration_s) if r.get("duration_in_traffic") else 0
        delay = max(0, delay)
        if delay >= 480:
            level = "heavy"
        elif delay >= 120:
            level = "moderate"
        else:
            level = "low"
        parsed.append({
            "route_id": r.get("id") or f"ola-{i + 1}",
            "traffic_level": level,
            "distance_km": round(float(distance or 0) / 1000.0, 2) if distance else None,
            "duration_seconds": duration_s,
            "delay_seconds": delay,
            "geometry": r.get("geometry") or r.get("overview_polyline"),
        })
    return parsed


async def get_traffic_at_location(lat: float, lon: float) -> Dict[str, Any]:
    if not OLA_API_KEY:
        raise ValueError("OLA_API_KEY is not set.")

    url = f"{OLA_BASE_URL}/tiles/v1/traffic"
    params = {"lat": lat, "lng": lon, "api_key": OLA_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        level = str(data.get("traffic_level") or data.get("congestion") or "moderate").lower()
        if level not in TRAFFIC_LEVELS:
            level = "moderate"
        return {
            "traffic_level": level,
            "delay_seconds": int(data.get("delay_seconds", TRAFFIC_DELAY_SECONDS[level])),
            "source": "ola",
            "lat": lat,
            "lon": lon,
        }
    except Exception as e:
        logger.warning("OLA traffic lookup failed: %s", e)
        raise e
