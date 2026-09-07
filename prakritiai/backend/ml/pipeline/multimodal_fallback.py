"""Fallback delivery modes (track, drone, helicopter) for villages confirmed
fully isolated from the vehicle road network.

Pure logic only — no FastAPI/DB imports — so it can be unit-tested standalone.
Reuses ml.pipeline.routing.build_graph (for the track graph) and the same
risk_aware_dijkstra pathfinder already used for vehicle routing, rather than
inventing a second pathfinding algorithm.
"""
import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import networkx as nx
import pandas as pd

from ml.pipeline.routing import risk_aware_dijkstra

MODE_PARAMS = {
    "track": {
        "fuel_cost_per_km": 3.0,
        "labor_cost_per_hour": 150.0,
        "trip_payload_kg": 50.0,
        "max_trips_in_window": 20,
    },
    "drone": {
        "base_sortie_cost": 500.0,
        "per_km_cost": 40.0,
        "cruise_kmph": 45.0,
        "max_range_km": 15.0,
        "payload_per_sortie_kg": 5.0,
        "max_sorties": 3,
        "min_clearance_m": 60.0,
        "max_climb_m": 600.0,
    },
    "helicopter": {
        "base_flight_cost": 25000.0,
        "per_km_cost": 300.0,
        "cruise_kmph": 180.0,
        "spinup_min": 20.0,
        "max_range_km": 80.0,
        "max_payload_kg": 500.0,
    },
}

# Rough per-unit weight so a "qty" of a commodity can be turned into a
# payload in kg for feasibility/trip-count checks. Deliberately simple —
# this is a hackathon cost model, not a real logistics weight table.
COMMODITY_UNIT_WEIGHT_KG = {"food": 1.0, "water": 1.0, "medicine": 0.2, "fuel": 1.0}


@dataclass
class ModeResult:
    mode: str
    feasible: bool
    cost: float
    eta_hours: float
    distance_km: float
    geometry: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _straight_line_geometry(lat1: float, lon1: float, lat2: float, lon2: float) -> Dict[str, Any]:
    return {"type": "LineString", "coordinates": [[lon1, lat1], [lon2, lat2]]}


MAX_SNAP_DISTANCE_KM = 1.5  # a sparse track network shouldn't be treated as
# reachable just because it happens to have *some* node somewhere in the
# demo area — without this, depot and village can both snap to the same
# distant, unrelated node and produce a false "feasible, zero-cost" route.


def _nearest_node(G: nx.DiGraph, lat: float, lon: float, max_km: float = MAX_SNAP_DISTANCE_KM) -> Optional[str]:
    """Snap a lat/lon to the nearest node in a graph built by
    ml.pipeline.routing.build_graph (nodes carry x=lon, y=lat), or None if
    nothing is within max_km."""
    best_node, best_dist = None, float("inf")
    for n, data in G.nodes(data=True):
        d = _haversine_km(lat, lon, data.get("y", 0.0), data.get("x", 0.0))
        if d < best_dist:
            best_node, best_dist = n, d
    return best_node if best_dist <= max_km else None


def build_elevation_lookup(df: pd.DataFrame) -> Callable[[float, float], float]:
    """Nearest-neighbor elevation lookup over a real (or synthetic-fallback)
    elevation grid, via scipy.spatial.cKDTree — deliberately not a true
    raster/GeoTIFF, to avoid adding rasterio/GDAL as a dependency."""
    from scipy.spatial import cKDTree

    coords = df[["lat", "lon"]].to_numpy()
    elevations = df["elevation_m"].to_numpy()
    tree = cKDTree(coords)

    def lookup(lat: float, lon: float) -> float:
        _, idx = tree.query([lat, lon])
        return float(elevations[idx])

    return lookup


def load_track_graph(path: str) -> nx.DiGraph:
    from ml.pipeline.routing import build_graph

    df = pd.read_parquet(path)
    return build_graph(df)


def load_helipads(path: str) -> List[Dict[str, Any]]:
    df = pd.read_parquet(path)
    return df.to_dict(orient="records")


def evaluate_track_option(
    depot: Dict[str, Any], village: Dict[str, Any], track_graph: nx.DiGraph, qty_kg: float,
) -> ModeResult:
    params = MODE_PARAMS["track"]
    if track_graph is None or track_graph.number_of_edges() == 0:
        return ModeResult("track", False, 0.0, 0.0, 0.0, reason="No track/path graph available")

    src = _nearest_node(track_graph, depot["lat"], depot["lon"])
    tgt = _nearest_node(track_graph, village["lat"], village["lon"])
    if src is None or tgt is None:
        return ModeResult("track", False, 0.0, 0.0, 0.0, reason=f"No track/path within {MAX_SNAP_DISTANCE_KM}km of depot or village")
    if src == tgt:
        return ModeResult("track", False, 0.0, 0.0, 0.0, reason="Depot and village snap to the same isolated track segment — not a real route")

    result = risk_aware_dijkstra(track_graph, src, tgt, min_survivability=0.0)
    if not result.path:
        return ModeResult("track", False, 0.0, 0.0, 0.0, reason="No walkable/track path exists between depot and village")

    distance_km = sum(
        float(track_graph[a][b].get("length_km", 0.0))
        for a, b in zip(result.path[:-1], result.path[1:])
    )
    num_trips = max(1, math.ceil(qty_kg / params["trip_payload_kg"]))
    if num_trips > params["max_trips_in_window"]:
        return ModeResult(
            "track", False, 0.0, result.travel_hours, distance_km,
            reason=f"Would need {num_trips} trips, exceeding the {params['max_trips_in_window']}-trip window — quantity too bulk for porter/2-wheeler relay",
        )
    cost = num_trips * (params["fuel_cost_per_km"] * distance_km + params["labor_cost_per_hour"] * result.travel_hours)
    geometry = {
        "type": "LineString",
        "coordinates": [
            [track_graph.nodes[n].get("x", 0.0), track_graph.nodes[n].get("y", 0.0)]
            for n in result.path
        ],
    }
    return ModeResult("track", True, round(cost, 2), round(result.travel_hours * num_trips, 2), round(distance_km, 2), geometry)


def evaluate_drone_option(
    depot: Dict[str, Any], village: Dict[str, Any], elevation_lookup: Callable[[float, float], float], qty_kg: float,
) -> ModeResult:
    params = MODE_PARAMS["drone"]
    distance_km = _haversine_km(depot["lat"], depot["lon"], village["lat"], village["lon"])
    geometry = _straight_line_geometry(depot["lat"], depot["lon"], village["lat"], village["lon"])

    if distance_km > params["max_range_km"]:
        return ModeResult("drone", False, 0.0, 0.0, distance_km, geometry, reason=f"{distance_km:.1f}km exceeds drone max range {params['max_range_km']}km")

    max_payload = params["payload_per_sortie_kg"] * params["max_sorties"]
    if qty_kg > max_payload:
        return ModeResult("drone", False, 0.0, 0.0, distance_km, geometry, reason=f"{qty_kg:.1f}kg exceeds max drone payload {max_payload:.1f}kg across {params['max_sorties']} sorties")

    if elevation_lookup is not None:
        depot_elev = elevation_lookup(depot["lat"], depot["lon"])
        n_samples = 10
        max_terrain = depot_elev
        for i in range(1, n_samples):
            t = i / n_samples
            lat = depot["lat"] + (village["lat"] - depot["lat"]) * t
            lon = depot["lon"] + (village["lon"] - depot["lon"]) * t
            max_terrain = max(max_terrain, elevation_lookup(lat, lon))
        required_altitude = max_terrain + params["min_clearance_m"]
        if required_altitude > depot_elev + params["max_climb_m"]:
            return ModeResult(
                "drone", False, 0.0, 0.0, distance_km, geometry,
                reason=f"Terrain along the corridor requires climbing {required_altitude - depot_elev:.0f}m, exceeding drone max climb {params['max_climb_m']}m",
            )

    num_sorties = max(1, math.ceil(qty_kg / params["payload_per_sortie_kg"]))
    cost = num_sorties * (params["base_sortie_cost"] + params["per_km_cost"] * distance_km)
    eta_hours = (distance_km / params["cruise_kmph"]) * num_sorties
    return ModeResult("drone", True, round(cost, 2), round(eta_hours, 2), round(distance_km, 2), geometry)


def evaluate_helicopter_option(
    depot: Dict[str, Any], village: Dict[str, Any], helipads: List[Dict[str, Any]], qty_kg: float,
) -> ModeResult:
    params = MODE_PARAMS["helicopter"]
    if not helipads:
        return ModeResult("helicopter", False, 0.0, 0.0, 0.0, reason="No helipad data available")

    nearest = min(helipads, key=lambda h: _haversine_km(depot["lat"], depot["lon"], h["lat"], h["lon"]))
    leg1_km = _haversine_km(depot["lat"], depot["lon"], nearest["lat"], nearest["lon"])
    leg2_km = _haversine_km(nearest["lat"], nearest["lon"], village["lat"], village["lon"])
    distance_km = leg1_km + leg2_km
    geometry = {
        "type": "LineString",
        "coordinates": [[depot["lon"], depot["lat"]], [nearest["lon"], nearest["lat"]], [village["lon"], village["lat"]]],
    }

    if distance_km > params["max_range_km"]:
        return ModeResult("helicopter", False, 0.0, 0.0, distance_km, geometry, reason=f"{distance_km:.1f}km exceeds helicopter max range {params['max_range_km']}km")
    if qty_kg > params["max_payload_kg"]:
        return ModeResult("helicopter", False, 0.0, 0.0, distance_km, geometry, reason=f"{qty_kg:.1f}kg exceeds helicopter max payload {params['max_payload_kg']}kg")

    cost = params["base_flight_cost"] + params["per_km_cost"] * distance_km
    eta_hours = distance_km / params["cruise_kmph"] + params["spinup_min"] / 60.0
    result = ModeResult("helicopter", True, round(cost, 2), round(eta_hours, 2), round(distance_km, 2), geometry)
    result.reason = f"Via {nearest.get('name', nearest.get('id'))} ({nearest.get('source', 'unknown')})"
    return result


def rank_fallback_options(
    depot: Dict[str, Any],
    village: Dict[str, Any],
    commodity: str,
    qty: float,
    track_graph: Optional[nx.DiGraph],
    elevation_lookup: Optional[Callable[[float, float], float]],
    helipads: List[Dict[str, Any]],
) -> Dict[str, Any]:
    unit_weight = COMMODITY_UNIT_WEIGHT_KG.get(commodity.lower(), 1.0)
    qty_kg = float(qty) * unit_weight

    results = [
        evaluate_track_option(depot, village, track_graph, qty_kg),
        evaluate_drone_option(depot, village, elevation_lookup, qty_kg),
        evaluate_helicopter_option(depot, village, helipads, qty_kg),
    ]
    feasible = [r for r in results if r.feasible]
    feasible.sort(key=lambda r: r.cost)
    recommended = feasible[0].mode if feasible else None

    def _to_dict(r: ModeResult) -> Dict[str, Any]:
        return {
            "mode": r.mode, "feasible": r.feasible, "cost": r.cost, "eta_hours": r.eta_hours,
            "distance_km": r.distance_km, "geometry": r.geometry, "reason": r.reason,
        }

    ranked_all = sorted(results, key=lambda r: (not r.feasible, r.cost))
    return {"ranked": [_to_dict(r) for r in ranked_all], "recommended": recommended}
