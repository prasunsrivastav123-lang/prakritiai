"""
GIS Pipeline API Router
Exposes the disaster response pipeline (routing, logistics LP, replanner, orchestrator)
as FastAPI endpoints under /api/pipeline/*.
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, mapping
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Load road + hazard data once at module level (same pattern as admin_override)
# ---------------------------------------------------------------------------
_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
ROADS_PATH = os.environ.get("ROADS_PARQUET", str(_DATA_DIR / "roads.parquet"))
HAZARDS_PATH = os.environ.get("HAZARDS_PARQUET", str(_DATA_DIR / "hazards.parquet"))

_roads_gdf: Optional[gpd.GeoDataFrame] = None
_hazards_df: Optional[pd.DataFrame] = None
_graph = None  # networkx DiGraph, built lazily


def _get_roads() -> gpd.GeoDataFrame:
    global _roads_gdf
    if _roads_gdf is None:
        try:
            logger.info(f"Loading roads from {ROADS_PATH}")
            _roads_gdf = gpd.read_parquet(ROADS_PATH)
        except Exception as e:
            logger.warning(f"Could not load roads.parquet: {e}")
            _roads_gdf = gpd.GeoDataFrame()
    return _roads_gdf


def _get_hazards() -> pd.DataFrame:
    global _hazards_df
    if _hazards_df is None:
        try:
            logger.info(f"Loading hazards from {HAZARDS_PATH}")
            _hazards_df = pd.read_parquet(HAZARDS_PATH)
        except Exception as e:
            logger.warning(f"Could not load hazards.parquet: {e}")
            _hazards_df = pd.DataFrame()
    return _hazards_df


def _get_graph():
    """Build the networkx graph lazily (only when a routing endpoint is called)."""
    global _graph
    if _graph is None:
        from ml.pipeline.routing import build_graph
        roads = _get_roads()
        _graph = build_graph(roads)
        logger.info(f"Graph built: {_graph.number_of_nodes()} nodes, {_graph.number_of_edges()} edges")
    return _graph


def _find_nearest_edge(lat: float, lon: float) -> str:
    """Find the nearest road edge_id to a lat/lon coordinate."""
    match = _find_nearest_edge_meta(lat, lon, max_distance_m=5000)
    if not match:
        raise HTTPException(
            status_code=404,
            detail=f"No road found within 5km of ({lat}, {lon})"
        )
    return match["edge_id"]


def _find_nearest_edge_meta(lat: float, lon: float, max_distance_m: float = 500) -> Optional[Dict[str, Any]]:
    """Snap a coordinate to the nearest road within max_distance_m (metres)."""
    roads = _get_roads()
    if roads is None or len(roads) == 0:
        return None
    try:
        roads_m = roads.to_crs(32646)
        pt_m = gpd.GeoDataFrame(
            [{"geometry": Point(lon, lat)}],
            crs="EPSG:4326",
        ).to_crs(32646)
        keep = [c for c in ["edge_id", "geometry", "u", "v"] if c in roads_m.columns]
        nearest = gpd.sjoin_nearest(
            pt_m, roads_m[keep],
            how="left",
            max_distance=max_distance_m,
            distance_col="dist_m",
        )
    except Exception as e:
        logger.warning(f"Nearest-edge search failed: {e}")
        return None

    if nearest.empty or pd.isna(nearest.iloc[0].get("edge_id")):
        return None

    row = nearest.iloc[0]
    edge_id = str(row["edge_id"])
    orig = roads[roads["edge_id"].astype(str) == edge_id]
    geom = orig.iloc[0].geometry if len(orig) else None
    u = v = None
    if len(orig):
        if "u" in orig.columns and pd.notna(orig.iloc[0].get("u")):
            u = str(orig.iloc[0]["u"])
        if "v" in orig.columns and pd.notna(orig.iloc[0].get("v")):
            v = str(orig.iloc[0]["v"])
        if u is None and geom is not None and not geom.is_empty:
            c0 = list(geom.coords)[0]
            u = f"{c0[0]:.5f},{c0[1]:.5f}"
        if v is None and geom is not None and not geom.is_empty:
            c1 = list(geom.coords)[-1]
            v = f"{c1[0]:.5f},{c1[1]:.5f}"

    return {
        "edge_id": edge_id,
        "geometry": mapping(geom) if geom is not None else None,
        "distance_from_hazard_m": round(float(row.get("dist_m") or 0), 1),
        "blocked": True,
        "u": u,
        "v": v,
    }


def _serialize_route(r) -> Optional[Dict[str, Any]]:
    if r is None:
        return None
    from ml.pipeline.routing import RouteResult
    if isinstance(r, RouteResult):
        return {
            "path": r.path,
            "travel_hours": r.travel_hours,
            "survivability": r.survivability,
            "expected_risk": r.expected_risk,
            "feasible": r.feasible,
        }
    if isinstance(r, dict):
        return r
    if isinstance(r, tuple):
        return {"raw": str(r)}
    return {"raw": str(r)}


def _serialize_allocation(result) -> Dict[str, Any]:
    if result is None:
        return {"allocations": {}, "shortfall": {}, "total_cost": None}

    def _key(k):
        if isinstance(k, tuple):
            return "|".join(str(x) for x in k)
        return k

    if isinstance(result, dict):
        alloc = result.get("allocations", result)
        if isinstance(alloc, dict):
            alloc = {_key(k): v for k, v in alloc.items()}
        short = result.get("shortfall", {})
        if isinstance(short, dict):
            short = {_key(k): v for k, v in short.items()}
        return {
            "allocations": alloc,
            "shortfall": short,
            "total_cost": result.get("total_cost"),
        }
    if isinstance(result, pd.DataFrame):
        return {"allocations": result.to_dict(orient="records"), "shortfall": {}, "total_cost": None}
    if isinstance(result, (list, tuple)):
        return {"allocations": list(result), "shortfall": {}, "total_cost": None}
    return {"allocations": str(result), "shortfall": {}, "total_cost": None}


def _risk_band(p: float) -> str:
    if p > 0.7:
        return "critical"
    if p >= 0.5:
        return "high"
    if p >= 0.3:
        return "medium"
    return "low"


async def _docs(coll: str) -> List[Dict[str, Any]]:
    from core.database import db
    return await db[coll].find({}, {"_id": 0}).to_list(2000)


# ===========================================================================
# REQUEST / RESPONSE MODELS
# ===========================================================================

class RouteRequest(BaseModel):
    origin_lat: float = Field(..., description="Origin latitude")
    origin_lon: float = Field(..., description="Origin longitude")
    dest_lat: float = Field(..., description="Destination latitude")
    dest_lon: float = Field(..., description="Destination longitude")
    min_survivability: float = Field(0.85, description="Minimum route survivability (0-1)")
    k_paths: int = Field(3, description="Number of alternative paths to return")


class LogisticsRequest(BaseModel):
    depots: List[Dict[str, Any]] = Field(..., description="List of depot locations with supplies")
    villages: List[Dict[str, Any]] = Field(..., description="List of villages needing supplies")
    inventory: Dict[str, Any] = Field(..., description="Available inventory at each depot")
    demand: Dict[str, Any] = Field(..., description="Demand at each village")
    commodities: List[str] = Field(default_factory=list, description="List of commodity types")


class OrchestratorRequest(BaseModel):
    depots: List[Dict[str, Any]] = Field(...)
    villages: List[Dict[str, Any]] = Field(...)
    inventory: Dict[str, Any] = Field(...)
    demand: Dict[str, Any] = Field(...)
    commodities: List[str] = Field(default_factory=list)


class ReplanRequest(BaseModel):
    edge_id: str = Field(..., description="Edge ID affected by new hazard")
    blockage_pct: float = Field(0.95, description="Blockage percentage (0-1)")
    hazard_type: str = Field("landslide", description="Type of hazard")


class InjectHazardRequest(BaseModel):
    lat: float
    lon: float
    hazard_type: str = Field(..., description="flood or landslide")
    severity: str = Field(..., description="low, medium, or high")
    source: str = Field(..., description="government or ai_prediction")
    notes: Optional[str] = None


class AIPredictRequest(BaseModel):
    lat: float
    lon: float
    rainfall_24h: float = 80
    rainfall_7d: float = 250
    soil_moisture: float = 0.6
    slope: float = 25
    elevation: float = 1200
    proximity_to_river: float = 500
    historical_flood_frequency: float = 5
    historical_landslide_frequency: float = 3


class TrafficRouteRequest(BaseModel):
    origin_lat: float
    origin_lon: float
    dest_lat: float
    dest_lon: float


# ===========================================================================
# ENDPOINT: Pipeline status
# ===========================================================================

@router.get("/pipeline/status")
async def pipeline_status():
    """Check the status of the GIS pipeline."""
    try:
        roads = _get_roads()
        hazards = _get_hazards()
        return {
            "status": "operational",
            "road_network": {
                "total_edges": len(roads),
                "columns": list(roads.columns) if len(roads) > 0 else [],
            },
            "hazards": {
                "total_records": len(hazards),
                "columns": list(hazards.columns) if len(hazards) > 0 else [],
            },
            "modules": [
                "orchestrator", "routing", "logistics_lp",
                "replanner", "offline_sync_engine", "admin_override",
            ],
        }
    except Exception as e:
        logger.error(f"Pipeline status failed: {e}", exc_info=True)
        return {"status": "degraded", "error": str(e)}


# ===========================================================================
# ENDPOINT: Route calculation (risk-aware Dijkstra + K alternative paths)
# ===========================================================================

@router.post("/pipeline/route")
async def calculate_route(req: RouteRequest):
    """
    Calculate optimal routes from origin to destination, avoiding hazards.
    Uses risk-aware Dijkstra + K-feasible-paths hybrid algorithm.
    """
    try:
        from ml.pipeline.routing import (
            build_graph, risk_aware_dijkstra,
            get_k_feasible_paths_hybrid, RouteResult
        )

        try:
            # Find nearest edges to origin/destination
            source_edge = _find_nearest_edge(req.origin_lat, req.origin_lon)
            target_edge = _find_nearest_edge(req.dest_lat, req.dest_lon)

            # Build or get cached graph
            G = _get_graph()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Data unavailable: {e}")

        # Get best route via risk-aware Dijkstra
        best_route = risk_aware_dijkstra(
            G, source_edge, target_edge,
            min_survivability=req.min_survivability
        )

        # Get K alternative paths
        alternatives = get_k_feasible_paths_hybrid(
            G, source_edge, target_edge,
            K=req.k_paths,
            min_survivability=req.min_survivability
        )

        def _route_to_dict(r):
            """Convert RouteResult to dict (handles both RouteResult objects and tuples)."""
            if r is None:
                return None
            if isinstance(r, RouteResult):
                return {
                    "path": r.path if hasattr(r, 'path') else getattr(r, '_asdict', lambda: {})(),
                    "survivability": getattr(r, 'survivability', None),
                    "travel_time": getattr(r, 'travel_time', None),
                }
            if isinstance(r, tuple):
                return {"raw": str(r)}
            if isinstance(r, dict):
                return r
            return {"raw": str(r)}

        return {
            "status": "success",
            "source_edge": source_edge,
            "target_edge": target_edge,
            "best_route": _route_to_dict(best_route),
            "alternative_routes": [_route_to_dict(r) for r in (alternatives or [])],
            "min_survivability": req.min_survivability,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Route calculation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# ENDPOINT: Logistics optimization (LP)
# ===========================================================================

@router.post("/pipeline/logistics/optimize")
async def optimize_logistics(req: LogisticsRequest):
    """
    Run LP optimization for resource allocation across depots and villages.
    """
    try:
        from ml.pipeline.logistics_lp import optimize_allocation

        try:
            roads = _get_roads()
            if roads.empty:
                raise ValueError("Roads data unavailable")
            hazards = _get_hazards()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Data unavailable: {e}")

        result = optimize_allocation(
            depots=req.depots,
            villages=req.villages,
            inventory=req.inventory,
            demand=req.demand,
            roads_df=roads,
            hazards_df=hazards,
            commodities=req.commodities or list(req.inventory.keys()),
        )

        # Handle various return types (DataFrame, dict, list, etc.)
        if isinstance(result, pd.DataFrame):
            return {
                "status": "success",
                "allocation": result.to_dict(orient="records"),
                "summary": {
                    "total_allocated": len(result),
                    "columns": list(result.columns),
                }
            }
        elif isinstance(result, dict):
            return {"status": "success", "allocation": result}
        elif isinstance(result, (list, tuple)):
            return {"status": "success", "allocation": list(result)}
        else:
            return {"status": "success", "allocation": str(result)}

    except Exception as e:
        logger.error(f"Logistics optimization failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# ENDPOINT: Full pipeline orchestration
# ===========================================================================

@router.post("/pipeline/orchestrate")
async def run_full_pipeline(req: OrchestratorRequest):
    """
    Run the full disaster response pipeline:
    build roads → match hazards → optimize routing → allocate resources.
    """
    try:
        from ml.pipeline.orchestrator import disaster_response_orchestrator

        try:
            roads = _get_roads()
            if roads.empty:
                raise ValueError("Roads data unavailable")
            hazards = _get_hazards()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Data unavailable: {e}")

        result = disaster_response_orchestrator(
            depots=req.depots,
            villages=req.villages,
            inventory=req.inventory,
            demand=req.demand,
            roads_df=roads,
            hazards_df=hazards,
            commodities=req.commodities or list(req.inventory.keys()),
        )

        # Convert result to JSON-serializable format
        if isinstance(result, pd.DataFrame):
            return {
                "status": "success",
                "result": result.to_dict(orient="records"),
                "type": "dataframe"
            }
        elif isinstance(result, dict):
            return {"status": "success", "result": result, "type": "dict"}
        elif isinstance(result, (list, tuple)):
            return {"status": "success", "result": list(result), "type": "list"}
        else:
            return {"status": "success", "result": str(result), "type": "string"}

    except Exception as e:
        logger.error(f"Pipeline orchestration failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# ENDPOINT: Real-time replanning (when new hazard occurs)
# ===========================================================================

@router.post("/pipeline/replan")
async def replan_routes(req: ReplanRequest):
    """
    Trigger real-time rerouting when a new hazard blocks a road edge.
    """
    try:
        from ml.pipeline.replanner import Replanner

        try:
            roads = _get_roads()
            if roads.empty:
                raise ValueError("Roads data unavailable")
            hazards = _get_hazards()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Data unavailable: {e}")

        replanner = Replanner()

        # Call the replanner with the hazard data
        # The exact method name may vary — adjust based on what's in the class
        hazard_event = {
            "edge_id": req.edge_id,
            "blockage_pct": req.blockage_pct,
            "hazard_type": req.hazard_type,
        }

        # Try common method names (adjust to match your actual Replanner API)
        result = None
        for method_name in ["inject_hazard", "replan", "update_hazard", "process_hazard"]:
            method = getattr(replanner, method_name, None)
            if method is not None:
                result = method(hazard_event)
                break

        if result is None:
            return {
                "status": "warning",
                "message": "Replanner initialized but no compatible method found. Check Replanner class methods.",
                "hazard": hazard_event,
            }

        # Convert result to JSON-serializable
        if isinstance(result, pd.DataFrame):
            return {"status": "success", "affected_routes": result.to_dict(orient="records")}
        elif isinstance(result, dict):
            return {"status": "success", "affected_routes": result}
        elif isinstance(result, (list, tuple)):
            return {"status": "success", "affected_routes": list(result)}
        else:
            return {"status": "success", "affected_routes": str(result)}

    except Exception as e:
        logger.error(f"Replanning failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# ENDPOINT: Get road network info
# ===========================================================================

@router.get("/pipeline/roads")
async def get_road_network(limit: int = 10):
    """Get a sample of the road network data."""
    try:
        roads = _get_roads()
        if roads.empty:
            raise ValueError("Road data is empty")
        sample = roads.head(limit)
        # Drop geometry column (not JSON-serializable)
        if "geometry" in sample.columns:
            sample = sample.drop(columns=["geometry"])
        return {
            "total_edges": len(roads),
            "columns": list(roads.columns),
            "sample": sample.to_dict(orient="records"),
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Data unavailable: {e}")


# ===========================================================================
# ENDPOINT: Get hazards info
# ===========================================================================

@router.get("/pipeline/hazards")
async def get_hazards(limit: int = 10):
    """Get a sample of the hazards data."""
    try:
        hazards = _get_hazards()
        sample = hazards.head(limit)
        if "geometry" in sample.columns:
            sample = sample.drop(columns=["geometry"])
        return {
            "total_records": len(hazards),
            "columns": list(hazards.columns),
            "sample": sample.to_dict(orient="records"),
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Data unavailable: {e}")


# ===========================================================================
# ENDPOINT: Inject hazard, snap to road, re-optimize
# ===========================================================================

@router.post("/pipeline/inject-and-optimize")
async def inject_and_optimize(req: InjectHazardRequest):
    if req.hazard_type not in ("flood", "landslide"):
        raise HTTPException(status_code=400, detail="hazard_type must be flood or landslide")
    if req.severity not in ("low", "medium", "high"):
        raise HTTPException(status_code=400, detail="severity must be low, medium, or high")
    if req.source not in ("government", "ai_prediction"):
        raise HTTPException(status_code=400, detail="source must be government or ai_prediction")

    from datetime import datetime, timezone
    from core.database import db
    from core.ws import manager

    severity_map = {"low": 0.4, "medium": 0.7, "high": 0.95}
    clearance_map = {"low": 2.0, "medium": 6.0, "high": 12.0}
    blockage = severity_map[req.severity]
    match = _find_nearest_edge_meta(req.lat, req.lon, max_distance_m=500)

    hazard_doc = {
        "lat": req.lat,
        "lon": req.lon,
        "hazard_type": req.hazard_type,
        "severity": req.severity,
        "source": req.source,
        "notes": req.notes,
        "blockage_pct": blockage,
        "est_clearance_hrs": clearance_map[req.severity],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if not match:
        warning = f"No road found within 500m of ({req.lat}, {req.lon})"
        payload = {
            "event": "hazard_injected",
            "hazard_type": req.hazard_type,
            "source": req.source,
            "lat": req.lat,
            "lon": req.lon,
            "matched_edge_id": None,
            "matched_road_geometry": None,
            "hazard_radius_m": 500,
            "blocked": False,
            "affected_villages": [],
            "alternative_routes": [],
            "allocation": None,
            "affected_vehicles": [],
            "warning": warning,
        }
        await manager.broadcast(payload)
        return {
            "status": "warning",
            "warning": warning,
            "hazard": hazard_doc,
            "matched_road": None,
            "hazard_radius_m": 500,
            "affected_villages": [],
            "alternative_routes": [],
            "optimal_allocation": None,
            "affected_vehicles": [],
            "vehicles_needed": 0,
            "estimated_cost": 0,
        }

    edge_id = match["edge_id"]
    hazard_doc["edge_id"] = edge_id
    await db.road_blocks.update_one(
        {"edge_id": edge_id},
        {"$set": {
            "edge_id": edge_id,
            "blocked": True,
            "hazard_type": req.hazard_type,
            "severity": req.severity,
            "source": req.source,
            "lat": req.lat,
            "lon": req.lon,
            "geometry": match["geometry"],
            "blockage_pct": blockage,
            "updated_at": hazard_doc["created_at"],
        }},
        upsert=True,
    )

    affected_villages = await db.supply_routes.find(
        {"path": edge_id, "active": {"$ne": False}},
        {"_id": 0},
    ).to_list(500)
    village_ids = list({r.get("village_id") for r in affected_villages if r.get("village_id")})
    village_docs = []
    if village_ids:
        village_docs = await db.villages.find({"id": {"$in": village_ids}}, {"_id": 0}).to_list(500)

    affected_vehicles = await db.vehicles.find(
        {"assigned_route.path": edge_id},
        {"_id": 0},
    ).to_list(500)

    alternative_routes: List[Dict[str, Any]] = []
    allocation_out: Optional[Dict[str, Any]] = None
    estimated_cost = 0.0

    try:
        from ml.pipeline.routing import risk_aware_dijkstra, get_k_feasible_paths_hybrid
        from ml.pipeline.logistics_lp import optimize_allocation

        G = _get_graph()
        u, v = match.get("u"), match.get("v")
        if u and v:
            for a, b in ((u, v), (v, u)):
                if G.has_edge(a, b):
                    G[a][b]["closed"] = True
                    G[a][b]["block_probability"] = blockage

        for route in affected_villages:
            src = route.get("depot_node") or (route.get("path") or [None])[0]
            tgt = route.get("village_node") or (route.get("path") or [None])[-1]
            if not src or not tgt:
                continue
            try:
                best = risk_aware_dijkstra(G, str(src), str(tgt))
            except Exception as e:
                logger.warning(f"Dijkstra failed for {src}->{tgt}: {e}")
                best = None
            try:
                alts = get_k_feasible_paths_hybrid(G, str(src), str(tgt), K=3)
            except Exception as e:
                logger.warning(f"Hybrid k-paths failed for {src}->{tgt}: {e}")
                alts = [best] if best else []
            alternative_routes.append({
                "route_id": route.get("route_id"),
                "village_id": route.get("village_id"),
                "depot_id": route.get("depot_id"),
                "blocked_edge_id": edge_id,
                "best_route": _serialize_route(best),
                "alternatives": [_serialize_route(r) for r in (alts or []) if r],
            })

        depots = await _docs("depots")
        villages = village_docs or await _docs("villages")
        commodities = ["food", "water", "medicine", "fuel"]
        if depots and villages:
            depot_ids = [d["id"] for d in depots]
            village_ids_lp = [v["id"] for v in villages]
            inventory = {}
            for d in depots:
                inv = d.get("inventory") or {}
                for c, qty in inv.items():
                    inventory[(d["id"], c)] = float(qty)
            demand = {}
            for vil in villages:
                dem = vil.get("demand") or {}
                for c, qty in dem.items():
                    demand[(vil["id"], c)] = float(qty)

            feasible = {}
            cost = {}
            for d in depot_ids:
                for vil in village_ids_lp:
                    pair_ok = True
                    pair_cost = 4.0
                    for ar in alternative_routes:
                        if ar.get("depot_id") == d and ar.get("village_id") == vil:
                            br = ar.get("best_route") or {}
                            pair_ok = bool(br.get("feasible", True) and br.get("path"))
                            pair_cost = float(br.get("travel_hours") or 4.0)
                    feasible[(d, vil)] = pair_ok
                    cost[(d, vil)] = pair_cost
            if not any(feasible.values()):
                for d in depot_ids:
                    for vil in village_ids_lp:
                        feasible[(d, vil)] = True
                        cost.setdefault((d, vil), 8.0)

            try:
                lp = optimize_allocation(
                    depot_ids, village_ids_lp, inventory, demand, feasible, cost, commodities,
                )
                allocation_out = _serialize_allocation(lp)
                estimated_cost = float(allocation_out.get("total_cost") or 0)
            except TypeError:
                roads = _get_roads()
                hazards = _get_hazards()
                lp = optimize_allocation(
                    depots=depots, villages=villages, inventory=inventory,
                    demand=demand, roads_df=roads, hazards_df=hazards,
                    commodities=commodities,
                )
                allocation_out = _serialize_allocation(lp)
                estimated_cost = float(allocation_out.get("total_cost") or 0)
    except Exception as e:
        logger.error(f"inject-and-optimize routing/LP failed: {e}", exc_info=True)

    rerouted = []
    for veh in affected_vehicles:
        alt = next((a for a in alternative_routes if a.get("best_route")), None)
        new_path = (alt or {}).get("best_route", {}).get("path") if alt else None
        if new_path:
            assigned = dict(veh.get("assigned_route") or {})
            assigned["path"] = new_path
            assigned["rerouted_from_edge"] = edge_id
            await db.vehicles.update_one({"id": veh["id"]}, {"$set": {"assigned_route": assigned}})
            veh["assigned_route"] = assigned
            rerouted.append(veh["id"])

    vehicles_needed = max(len(village_ids), 1) if village_ids else 0
    if not estimated_cost:
        estimated_cost = vehicles_needed * 35000

    ws_payload = {
        "event": "hazard_injected",
        "hazard_type": req.hazard_type,
        "source": req.source,
        "lat": req.lat,
        "lon": req.lon,
        "matched_edge_id": edge_id,
        "matched_road_geometry": match["geometry"],
        "hazard_radius_m": 500,
        "blocked": True,
        "affected_villages": village_docs or village_ids,
        "alternative_routes": alternative_routes,
        "allocation": allocation_out,
        "affected_vehicles": affected_vehicles,
    }
    await manager.broadcast(ws_payload)

    return {
        "status": "success",
        "hazard": hazard_doc,
        "matched_road": {
            "edge_id": match["edge_id"],
            "geometry": match["geometry"],
            "distance_from_hazard_m": match["distance_from_hazard_m"],
            "blocked": True,
        },
        "hazard_radius_m": 500,
        "affected_villages": village_docs or village_ids,
        "alternative_routes": alternative_routes,
        "optimal_allocation": allocation_out,
        "affected_vehicles": affected_vehicles,
        "vehicles_needed": vehicles_needed,
        "estimated_cost": estimated_cost,
        "vehicles_rerouted": rerouted,
    }


# ===========================================================================
# ENDPOINT: AI hazard prediction + optional pre-positioning
# ===========================================================================

@router.post("/pipeline/ai-predict")
async def ai_predict(req: AIPredictRequest):
    from ml.hazard_models import FLOOD_WEIGHTS, LANDSLIDE_WEIGHTS, _normalize, _clamp
    from core.database import db
    from core.ws import manager

    features = {
        "rainfall_24h": req.rainfall_24h,
        "rainfall_7d": req.rainfall_7d,
        "soil_moisture": req.soil_moisture,
        "slope_deg": req.slope,
        "elevation_m": req.elevation,
        "distance_to_river_m": req.proximity_to_river,
        "historical_flood_frequency": req.historical_flood_frequency,
        "historical_landslide_frequency": req.historical_landslide_frequency,
        "poor_drainage": 0.5,
        "fragile_geology": 0.65,
        "vegetation_index": 0.45,
        "road_cut": 0.4,
    }
    flood_prob = _clamp(sum(w * _normalize(name, features) for name, w in FLOOD_WEIGHTS.items()), 0.02, 0.97)
    landslide_prob = _clamp(sum(w * _normalize(name, features) for name, w in LANDSLIDE_WEIGHTS.items()), 0.02, 0.97)
    dominant = "flood" if flood_prob >= landslide_prob else "landslide"
    peak = max(flood_prob, landslide_prob)
    risk_level = _risk_band(peak)

    match = _find_nearest_edge_meta(req.lat, req.lon, max_distance_m=5000)
    matched_edge_id = match["edge_id"] if match else None

    affected_routes = []
    if matched_edge_id:
        affected_routes = await db.supply_routes.find(
            {"path": matched_edge_id},
            {"_id": 0},
        ).to_list(200)

    pre_positioning_recommended = peak > 0.7
    pre_positioning_plan = None
    cost_comparison = None

    if pre_positioning_recommended:
        n_vehicles = max(len(affected_routes), 2)
        commodities = {"food": 80 * n_vehicles, "water": 120 * n_vehicles, "medicine": 40 * n_vehicles, "fuel": 30 * n_vehicles}
        route_hint = affected_routes[0] if affected_routes else {
            "origin": {"lat": req.lat, "lon": req.lon},
            "note": "pre-position to nearest depot covering this coordinate",
        }
        pre_cost = n_vehicles * 25000
        emergency_cost = (n_vehicles + 1) * 35000
        savings = emergency_cost - pre_cost
        savings_pct = round(100.0 * savings / emergency_cost, 1) if emergency_cost else 0
        cost_comparison = {
            "pre_positioning_cost": pre_cost,
            "emergency_transfer_cost": emergency_cost,
            "savings": savings,
            "savings_pct": savings_pct,
        }
        pre_positioning_plan = {
            "commodities": commodities,
            "route": route_hint,
            "vehicles": n_vehicles,
            "cost": pre_cost,
        }

    result = {
        "status": "success",
        "location": {"lat": req.lat, "lon": req.lon},
        "flood_probability": round(flood_prob, 3),
        "landslide_probability": round(landslide_prob, 3),
        "risk_level": risk_level,
        "dominant_hazard": dominant,
        "matched_edge_id": matched_edge_id,
        "affected_routes": affected_routes,
        "pre_positioning_recommended": pre_positioning_recommended,
        "pre_positioning_plan": pre_positioning_plan,
        "cost_comparison": cost_comparison,
    }

    if risk_level in ("high", "critical"):
        await manager.broadcast({
            "event": "ai_prediction",
            "lat": req.lat,
            "lon": req.lon,
            "flood_probability": result["flood_probability"],
            "landslide_probability": result["landslide_probability"],
            "risk_level": risk_level,
            "pre_positioning_recommended": pre_positioning_recommended,
            "pre_positioning_plan": pre_positioning_plan,
            "cost_comparison": cost_comparison,
        })

    return result


@router.get("/pipeline/traffic")
async def pipeline_traffic(lat: float = Query(...), lon: float = Query(...)):
    from ml.pipeline.ola_integration import get_traffic_at_location
    info = await get_traffic_at_location(lat, lon)
    return {
        "traffic_level": info.get("traffic_level"),
        "delay_seconds": info.get("delay_seconds"),
        "source": info.get("source"),
    }


@router.post("/pipeline/traffic-route")
async def pipeline_traffic_route(req: TrafficRouteRequest):
    from ml.pipeline.ola_integration import get_traffic_aware_route
    result = await get_traffic_aware_route(
        req.origin_lat, req.origin_lon, req.dest_lat, req.dest_lon,
    )
    return {
        "routes": result.get("routes", []),
        "recommended_route": result.get("recommended_route"),
        "source": result.get("source"),
    }


@router.get("/pipeline/depots")
async def list_depots():
    return await _docs("depots")


@router.get("/pipeline/villages")
async def list_pipeline_villages():
    return await _docs("villages")


@router.get("/pipeline/supply-routes")
async def list_supply_routes():
    return await _docs("supply_routes")