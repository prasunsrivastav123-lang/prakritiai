"""Canonical downloader for the multi-modal isolation-fallback demo area.

Downloads a small, tightly-bounded real-data extract centered on Shillong:
  1. a drivable vehicle road graph
  2. a walkable / 2-wheeler track graph (path/track/footway/bridleway/cycleway)
  3. a list of real OSM places inside the disk (for picking a demo village)
  4. an elevation grid (real public SRTM API, synthetic fallback if unreachable)
  5. nearby helipads/aerodromes (real OSM, mock fallback if none found)

Run manually, once, ahead of the demo — everything it produces is a small,
checked-in file so the live demo itself makes zero external network calls.

    python download_demo_area.py
"""
import logging
import math
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd
import requests
from shapely.geometry import Point

# osmnx pins a single resolved IP for the Overpass hostname (to keep
# round-robin backends consistent across the "check pause" and "send query"
# calls) by monkeypatching socket.getaddrinfo. In this environment that
# pinned IP is consistently unreachable even though the hostname resolves
# fine and other IPs in the round-robin are reachable (verified: plain
# `requests`/`curl` calls to the same hosts succeed in under a second).
# Neutralizing the patch lets each connection resolve normally instead of
# being pinned to the one bad IP.
import osmnx._http as _ox_http
import osmnx._overpass as _ox_overpass
_ox_http._config_dns = lambda url: None
_ox_overpass._config_dns = lambda url: None

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("download_demo_area")

DEMO_CENTER = (25.5788, 91.8933)  # (lat, lon) — same point as download_shillong_parquet.py
DEMO_RADIUS_M = 12000
HELIPAD_SEARCH_RADIUS_M = 50000
MAX_ACCEPTABLE_EDGES = 100000  # generous relative to the earlier 7.4M-edge regional-extract incident; a 12km-radius disk around a town is still tiny in-memory
ELEVATION_GRID_SPACING_M = 500

DATA_DIR = Path(__file__).resolve().parent / "data" / "processed"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Track-only classes — deliberately excludes "unclassified" (already part of
# osmnx's drive-network filter) so the track graph never overlaps the vehicle
# graph. That overlap would silently keep an "isolated" village reachable by
# a road the vehicle router already tried, defeating the demo.
TRACK_SPEEDS_KMPH = {"footway": 4, "path": 5, "track": 8, "bridleway": 6, "cycleway": 12}
TRACK_HIGHWAY_FILTER = '["highway"~"track|path|footway|bridleway|cycleway"]'

DRIVE_SPEEDS_KMPH = {
    "motorway": 80, "trunk": 70, "primary": 55, "secondary": 45,
    "tertiary": 35, "unclassified": 20, "residential": 25, "service": 15,
    "motorway_link": 50, "trunk_link": 45, "primary_link": 40,
    "secondary_link": 35, "tertiary_link": 30,
}

OVERPASS_MIRRORS = [
    "https://overpass-api.de/api",
    "https://overpass.kumi.systems/api",
    "https://overpass.openstreetmap.ru/api",
]


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _with_overpass_retries(fn, *args, **kwargs):
    """Try each known Overpass mirror in turn; osmnx reads the endpoint from
    ox.settings.overpass_url at call time."""
    ox.settings.requests_timeout = 45  # fail reasonably fast on a dead mirror; we have 3 to try
    last_err = None
    for mirror in OVERPASS_MIRRORS:
        ox.settings.overpass_url = mirror
        try:
            logger.info(f"Trying Overpass mirror {mirror} ...")
            return fn(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Mirror {mirror} failed: {e}")
            last_err = e
            time.sleep(2)
    raise last_err


def _edges_to_gdf(G, speed_table, default_speed_kmph):
    """Shape an osmnx MultiDiGraph into the flat schema routing.build_graph()
    and roads.parquet already expect (including per-node x/y, which
    build_graph needs for its A*/HybridRoutingEngine heuristic). Elevation is
    left at 0.0 here — the real elevation data for this feature lives in the
    dedicated elevation grid used for drone terrain-clearance, not on
    individual road edges.

    osmnx's graph already carries a separate (u,v) and (v,u) edge for every
    two-way street. Emitting both as their own rows here would give the same
    physical segment two different edge_id strings depending on direction —
    breaking any exact-string match against a stored edge_id (e.g. a
    supply_routes.path entry) whenever the hazard-injection nearest-edge
    search happens to snap to the "other" direction's row. Deduplicate to one
    row per undirected pair; build_graph()'s own bidirectional flag is what
    adds both directions back at the graph level for routing.
    """
    nodes, edges = ox.graph_to_gdfs(G)
    edges = edges.reset_index()
    seen_pairs = set()
    rows = []
    for _, r in edges.iterrows():
        pair = frozenset((r["u"], r["v"]))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        hw = r.get("highway")
        if isinstance(hw, list):
            hw = hw[0] if hw else None
        speed = speed_table.get(hw, default_speed_kmph)
        length_m = float(r.get("length", 0) or 0)
        length_km = length_m / 1000.0
        u_node = nodes.loc[r["u"]]
        v_node = nodes.loc[r["v"]]
        rows.append({
            "edge_id": f"e-{r['u']}-{r['v']}-{r.get('key', 0)}",
            "u": str(r["u"]),
            "v": str(r["v"]),
            "geometry": r["geometry"],
            "length": length_m,
            "length_km": length_km,
            "highway": hw,
            "speed_kmph": float(speed),
            "travel_time_min": (length_km / max(speed, 1.0)) * 60.0,
            "bidirectional": True,
            "bridge_id": None,
            "elevation_u": 0.0,
            "elevation_v": 0.0,
            "x_u": float(u_node["x"]), "y_u": float(u_node["y"]),
            "x_v": float(v_node["x"]), "y_v": float(v_node["y"]),
        })
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=edges.crs)


def download_vehicle_graph() -> gpd.GeoDataFrame:
    logger.info(f"Downloading vehicle (drive) graph: {DEMO_RADIUS_M}m around {DEMO_CENTER}")
    G = _with_overpass_retries(
        ox.graph_from_point, DEMO_CENTER, dist=DEMO_RADIUS_M, network_type="drive", simplify=True,
    )
    gdf = _edges_to_gdf(G, DRIVE_SPEEDS_KMPH, default_speed_kmph=20.0)
    if len(gdf) > MAX_ACCEPTABLE_EDGES:
        raise RuntimeError(
            f"Vehicle graph has {len(gdf)} edges, exceeding MAX_ACCEPTABLE_EDGES="
            f"{MAX_ACCEPTABLE_EDGES}. Refusing to save — shrink DEMO_RADIUS_M."
        )
    out_path = DATA_DIR / "demo_vehicle_roads.parquet"
    gdf.to_parquet(out_path)
    logger.info(f"Saved vehicle graph: {len(gdf)} edges -> {out_path}")
    return gdf


def download_track_graph() -> gpd.GeoDataFrame:
    logger.info(f"Downloading track/path graph: {DEMO_RADIUS_M}m around {DEMO_CENTER}")
    G = _with_overpass_retries(
        ox.graph_from_point, DEMO_CENTER, dist=DEMO_RADIUS_M,
        custom_filter=TRACK_HIGHWAY_FILTER, simplify=True,
    )
    gdf = _edges_to_gdf(G, TRACK_SPEEDS_KMPH, default_speed_kmph=5.0)
    if len(gdf) > MAX_ACCEPTABLE_EDGES:
        raise RuntimeError(
            f"Track graph has {len(gdf)} edges, exceeding MAX_ACCEPTABLE_EDGES="
            f"{MAX_ACCEPTABLE_EDGES}. Refusing to save — shrink DEMO_RADIUS_M."
        )
    out_path = DATA_DIR / "demo_track_paths.parquet"
    gdf.to_parquet(out_path)
    logger.info(f"Saved track graph: {len(gdf)} edges -> {out_path}")
    return gdf


def discover_candidate_villages() -> pd.DataFrame:
    logger.info(f"Discovering real OSM places inside {DEMO_RADIUS_M}m of {DEMO_CENTER}")
    tags = {"place": ["village", "hamlet", "suburb", "town"]}
    gdf = _with_overpass_retries(
        ox.features_from_point, DEMO_CENTER, tags=tags, dist=DEMO_RADIUS_M,
    )
    rows = []
    for idx, r in gdf.iterrows():
        geom = r.geometry
        if geom is None or geom.is_empty:
            continue
        pt = geom if geom.geom_type == "Point" else geom.centroid
        dist_km = _haversine_km(DEMO_CENTER[0], DEMO_CENTER[1], pt.y, pt.x)
        rows.append({
            "osm_id": idx[1] if isinstance(idx, tuple) else idx,
            "name": r.get("name") or r.get("name:en") or "(unnamed)",
            "place_type": r.get("place"),
            "lat": pt.y, "lon": pt.x,
            "distance_from_center_km": round(dist_km, 2),
        })
    df = pd.DataFrame(rows).sort_values("distance_from_center_km")
    out_path = DATA_DIR / "demo_candidate_villages.csv"
    df.to_csv(out_path, index=False)
    logger.info(f"Found {len(df)} candidate places -> {out_path}")
    for _, r in df.iterrows():
        logger.info(f"  {r['name']!r:30s} ({r['place_type']}) at {r['lat']:.4f},{r['lon']:.4f} — {r['distance_from_center_km']}km")
    return df


def _synthetic_elevation(lat, lon):
    """Deterministic procedural terrain, only used if the real API fetch
    fails. Loosely shaped around Shillong's real ~1500-1965m plateau."""
    base = 1500.0
    dlat = (lat - DEMO_CENTER[0]) * 200.0
    dlon = (lon - DEMO_CENTER[1]) * 200.0
    return base + 200.0 * math.sin(dlat) * math.cos(dlon) + 50.0 * math.sin(dlat * 3.1 + dlon * 2.3)


def download_elevation_grid() -> pd.DataFrame:
    logger.info(f"Building elevation grid: {ELEVATION_GRID_SPACING_M}m spacing over {DEMO_RADIUS_M}m disk")
    deg_per_m_lat = 1.0 / 111320.0
    deg_per_m_lon = 1.0 / (111320.0 * math.cos(math.radians(DEMO_CENTER[0])))
    step_lat = ELEVATION_GRID_SPACING_M * deg_per_m_lat
    step_lon = ELEVATION_GRID_SPACING_M * deg_per_m_lon
    n = int(DEMO_RADIUS_M / ELEVATION_GRID_SPACING_M) + 1

    points = []
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            lat = DEMO_CENTER[0] + i * step_lat
            lon = DEMO_CENTER[1] + j * step_lon
            if _haversine_km(DEMO_CENTER[0], DEMO_CENTER[1], lat, lon) * 1000.0 <= DEMO_RADIUS_M:
                points.append((lat, lon))
    logger.info(f"Grid has {len(points)} points inside the disk")

    rows = []
    source = "opentopodata_srtm"
    try:
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            locations = "|".join(f"{lat:.6f},{lon:.6f}" for lat, lon in batch)
            resp = requests.get(
                "https://api.opentopodata.org/v1/srtm90m",
                params={"locations": locations},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") != "OK":
                raise RuntimeError(f"OpenTopoData returned status={data.get('status')}")
            for (lat, lon), result in zip(batch, data["results"]):
                elev = result.get("elevation")
                if elev is None:
                    raise RuntimeError("OpenTopoData returned a null elevation")
                rows.append({"lat": lat, "lon": lon, "elevation_m": float(elev)})
            time.sleep(1.0)  # be polite to the free public API
        logger.info(f"Fetched {len(rows)} real elevation points from OpenTopoData SRTM")
    except Exception as e:
        logger.warning(f"Real elevation fetch failed ({e}); falling back to synthetic terrain")
        rows = [
            {"lat": lat, "lon": lon, "elevation_m": _synthetic_elevation(lat, lon)}
            for lat, lon in points
        ]
        source = "synthetic_fallback"

    df = pd.DataFrame(rows)
    df["source"] = source
    out_path = DATA_DIR / "demo_elevation_grid.parquet"
    df.to_parquet(out_path)
    logger.info(f"Saved elevation grid: {len(df)} points, source={source} -> {out_path}")
    return df


def download_helipads() -> pd.DataFrame:
    logger.info(f"Searching for real helipads/aerodromes within {HELIPAD_SEARCH_RADIUS_M}m")
    tags = {"aeroway": ["helipad", "heliport", "aerodrome"]}
    rows = []
    source = "real_osm"
    try:
        gdf = _with_overpass_retries(
            ox.features_from_point, DEMO_CENTER, tags=tags, dist=HELIPAD_SEARCH_RADIUS_M,
        )
        if len(gdf) == 0:
            raise RuntimeError("Overpass returned zero aeroway features in range")
        for idx, r in gdf.iterrows():
            geom = r.geometry
            if geom is None or geom.is_empty:
                continue
            pt = geom if geom.geom_type == "Point" else geom.centroid
            rows.append({
                "id": f"heli-{idx[1] if isinstance(idx, tuple) else idx}",
                "name": r.get("name") or "(unnamed)",
                "aeroway": r.get("aeroway"),
                "lat": pt.y, "lon": pt.x,
                "distance_from_center_km": round(
                    _haversine_km(DEMO_CENTER[0], DEMO_CENTER[1], pt.y, pt.x), 2
                ),
            })
    except Exception as e:
        logger.warning(f"Real helipad search failed or found nothing ({e}); using mock fallback")
        source = "mock_fallback"

    if not rows:
        # One clearly-labeled mock point a few km from the depot, so the
        # helicopter mode always has at least one candidate in the demo.
        mock_lat = DEMO_CENTER[0] + 0.03
        mock_lon = DEMO_CENTER[1] + 0.02
        rows = [{
            "id": "heli-mock-1",
            "name": "MOCK Helipad (no real OSM helipad found in range)",
            "aeroway": "helipad",
            "lat": mock_lat, "lon": mock_lon,
            "distance_from_center_km": round(
                _haversine_km(DEMO_CENTER[0], DEMO_CENTER[1], mock_lat, mock_lon), 2
            ),
        }]
        source = "mock_fallback"

    df = pd.DataFrame(rows)
    df["source"] = source
    out_path = DATA_DIR / "demo_helipads.parquet"
    df.to_parquet(out_path)
    logger.info(f"Saved {len(df)} helipad(s), source={source} -> {out_path}")
    return df


if __name__ == "__main__":
    logger.info("=== Demo area download starting ===")
    download_vehicle_graph()
    download_track_graph()
    discover_candidate_villages()
    download_elevation_grid()
    download_helipads()
    logger.info("=== Demo area download complete ===")
