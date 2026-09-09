"""
GIS Pipeline API Router
Exposes the disaster response pipeline (routing, logistics LP, replanner, orchestrator)
as FastAPI endpoints under /api/pipeline/*.
"""

import os
import json
import logging
import math
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

TRACK_PATHS_PATH = os.environ.get("TRACK_PATHS_PARQUET", str(_DATA_DIR / "demo_track_paths.parquet"))
ELEVATION_GRID_PATH = os.environ.get("ELEVATION_GRID_PARQUET", str(_DATA_DIR / "demo_elevation_grid.parquet"))
HELIPADS_PATH = os.environ.get("HELIPADS_PARQUET", str(_DATA_DIR / "demo_helipads.parquet"))

_track_graph = None
_elevation_lookup = None
_helipads: Optional[List[Dict[str, Any]]] = None


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


def _get_track_graph():
    """Lazily load the walkable/2-wheeler track graph (path/track/footway/
    bridleway/cycleway) used for the isolated-village fallback demo."""
    global _track_graph
    if _track_graph is None:
        from ml.pipeline.multimodal_fallback import load_track_graph
        try:
            _track_graph = load_track_graph(TRACK_PATHS_PATH)
            logger.info(f"Loaded track graph: {_track_graph.number_of_edges()} edges from {TRACK_PATHS_PATH}")
        except Exception as e:
            logger.warning(f"Could not load track graph: {e}")
            import networkx as nx
            _track_graph = nx.DiGraph()
    return _track_graph


def _get_elevation_lookup():
    """Lazily load the elevation grid used for drone terrain-clearance checks."""
    global _elevation_lookup
    if _elevation_lookup is None:
        from ml.pipeline.multimodal_fallback import build_elevation_lookup
        try:
            df = pd.read_parquet(ELEVATION_GRID_PATH)
            _elevation_lookup = build_elevation_lookup(df)
            source = df["source"].mode().iloc[0] if "source" in df.columns and len(df) else "unknown"
            logger.info(f"Loaded elevation grid: {len(df)} points, source={source}")
        except Exception as e:
            logger.warning(f"Could not load elevation grid: {e}")
            _elevation_lookup = None
    return _elevation_lookup


def _get_helipads() -> List[Dict[str, Any]]:
    """Lazily load helipad/aerodrome points used for the helicopter fallback mode."""
    global _helipads
    if _helipads is None:
        from ml.pipeline.multimodal_fallback import load_helipads
        try:
            _helipads = load_helipads(HELIPADS_PATH)
            sources = {h.get("source") for h in _helipads}
            logger.info(f"Loaded helipads: {len(_helipads)}, source={sources}")
        except Exception as e:
            logger.warning(f"Could not load helipads: {e}")
            _helipads = []
    return _helipads


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
        # travel_hours is float("inf") for a genuinely infeasible route (no
        # path exists) — exactly the case for a fully-isolated village, and
        # not valid JSON. Every other numeric field here is already bounded.
        travel_hours = r.travel_hours if math.isfinite(r.travel_hours) else None
        return {
            "path": r.path,
            "travel_hours": travel_hours,
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
    severity: str = Field(..., description="low, medium, high, or critical")
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
        from shapely.ops import linemerge

        try:
            # Snap origin/destination to the nearest road, then take that
            # edge's node id (not the edge_id string) — risk_aware_dijkstra /
            # get_k_feasible_paths_hybrid traverse nx nodes, matching the
            # fix already applied to inject-and-optimize's commodity routing.
            source_match = _find_nearest_edge_meta(req.origin_lat, req.origin_lon, max_distance_m=5000)
            target_match = _find_nearest_edge_meta(req.dest_lat, req.dest_lon, max_distance_m=5000)
            if not source_match or not target_match:
                raise HTTPException(status_code=404, detail="No road found within 5km of origin or destination")
            source_node = str(source_match.get("u") or source_match.get("v"))
            target_node = str(target_match.get("u") or target_match.get("v"))

            # Build or get cached graph
            G = _get_graph()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Data unavailable: {e}")

        # Get best route via risk-aware Dijkstra (edge survivability grows
        # with each edge's AI-predicted risk_growth_per_hour — see
        # ml.pipeline.routing.edge_survival)
        best_route = risk_aware_dijkstra(
            G, source_node, target_node,
            min_survivability=req.min_survivability
        )

        # Get an alternative via the hybrid A* engine (same risk model)
        alternatives = get_k_feasible_paths_hybrid(
            G, source_node, target_node,
            K=req.k_paths,
            min_survivability=req.min_survivability
        )

        # Build an O(1) (u,v)-pair -> geometry index once, instead of a full
        # table scan per edge — a 180-edge path over 15k road rows means the
        # naive per-edge boolean-filter approach does ~2.7M row comparisons
        # per route (worse for two routes), which is where the multi-second
        # lag actually came from when this was first measured live.
        roads_df = _get_roads()
        edge_geom_by_pair = {
            frozenset((row.u, row.v)): row.geometry
            for row in roads_df.itertuples(index=False)
            if row.geometry is not None and not row.geometry.is_empty
        }

        def _path_geometry(path):
            """Merge each edge's real road geometry along a node path into one polyline."""
            if not path or len(path) < 2:
                return None
            segments = []
            for i in range(len(path) - 1):
                geom = edge_geom_by_pair.get(frozenset((path[i], path[i + 1])))
                if geom is not None:
                    segments.append(geom)
            if not segments:
                return None
            try:
                return mapping(linemerge(segments))
            except Exception:
                return None

        def _route_to_dict(r):
            """Convert RouteResult to dict (handles both RouteResult objects and tuples)."""
            if r is None:
                return None
            if isinstance(r, RouteResult):
                return {
                    "path": r.path if hasattr(r, 'path') else getattr(r, '_asdict', lambda: {})(),
                    "survivability": getattr(r, 'survivability', None),
                    "travel_time": getattr(r, 'travel_hours', None),
                    "feasible": getattr(r, 'feasible', None),
                    "geometry": _path_geometry(getattr(r, 'path', None)),
                }
            if isinstance(r, tuple):
                return {"raw": str(r)}
            if isinstance(r, dict):
                return r
            return {"raw": str(r)}

        return {
            "status": "success",
            "source_node": source_node,
            "target_node": target_node,
            "origin": {"lat": req.origin_lat, "lon": req.origin_lon},
            "destination": {"lat": req.dest_lat, "lon": req.dest_lon},
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
    if req.severity not in ("low", "medium", "high", "critical"):
        raise HTTPException(status_code=400, detail="severity must be low, medium, high, or critical")
    if req.source not in ("government", "ai_prediction"):
        raise HTTPException(status_code=400, detail="source must be government or ai_prediction")

    from datetime import datetime, timezone
    from core.database import db
    from core.ws import manager

    severity_map = {"low": 0.4, "medium": 0.7, "high": 0.95, "critical": 1.0}
    clearance_map = {"low": 2.0, "medium": 6.0, "high": 12.0, "critical": 9999.0}
    # Per-hour rate at which this hazard's effective block probability keeps
    # climbing the longer a vehicle takes to reach it (e.g. continued rain
    # worsening a landslide) — consumed by ml.pipeline.routing.edge_survival.
    risk_growth_map = {"low": 0.01, "medium": 0.03, "high": 0.05, "critical": 0.08}
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

    from ml.pipeline.resilience import HAZARD_PRIORITY
    information_sources = [req.source]
    existing_hazard = None
    if match:
        existing_hazard = await db.road_blocks.find_one({"edge_id": match["edge_id"]})
        if existing_hazard:
            ext_src = existing_hazard.get("source")
            if ext_src and ext_src != req.source:
                information_sources.append(ext_src)
            if HAZARD_PRIORITY.get(ext_src, 0) > HAZARD_PRIORITY.get(req.source, 0):
                hazard_doc["status"] = "SUPERSEDED"
                hazard_doc["superseded_by"] = ext_src
            elif HAZARD_PRIORITY.get(req.source, 0) > HAZARD_PRIORITY.get(ext_src, 0):
                await db.road_blocks.update_one(
                    {"edge_id": match["edge_id"]},
                    {"$set": {"status": "SUPERSEDED", "superseded_by": req.source}}
                )

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
    
    # EC10 Fix: Only upsert into DB if the hazard is NOT superseded
    if hazard_doc.get("status") != "SUPERSEDED":
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
    srlg_warnings = []

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
                    G[a][b]["risk_growth_per_hour"] = risk_growth_map[req.severity]
                    # edge_survival()'s sigmoid treats a block as "likely
                    # already cleared" once arrival_hours exceeds
                    # reopen_after_hours — which defaults to 0 on edges that
                    # never had a real clearance estimate, making
                    # block_probability inert for any nonzero travel time.
                    # Propagate the same clearance estimate already computed
                    # for the road_blocks doc so a live route re-check
                    # actually treats this edge as blocked.
                    G[a][b]["reopen_after_hours"] = clearance_map[req.severity]
                    if G[a][b].get("bridge_id"):
                        if f"SRLG Warning: Hazard on shared bridge {G[a][b]['bridge_id']}" not in srlg_warnings:
                            srlg_warnings.append(f"SRLG Warning: Hazard on shared bridge {G[a][b]['bridge_id']}")

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
                # If village is evacuated, do not send supplies to a ghost town!
                state = vil.get("village_state", "NORMAL")
                if state in ["EVACUATED", "EVACUATING"]:
                    continue
                    
                dem = vil.get("demand") or {}
                for c, qty in dem.items():
                    demand[(vil["id"], c)] = float(qty)
            
            from ml.pipeline.resilience import count_blocked_routes, calculate_weighted_priority, calculate_depot_state, calculate_effective_inventory
            all_routes = await db.supply_routes.find({"active": {"$ne": False}}, {"_id": 0}).to_list(1000)
            blocked_docs = await db.road_blocks.find({"blocked": True}, {"_id": 0}).to_list(1000)
            blocked_edges = [b["edge_id"] for b in blocked_docs]
            if edge_id not in blocked_edges:
                blocked_edges.append(edge_id)

            depot_states = {}
            for d in depots:
                d_id = d["id"]
                d_state = calculate_depot_state(d_id, all_routes, blocked_edges)
                depot_states[d_id] = d_state.name
                eff_inv = calculate_effective_inventory(d.get("inventory") or {}, d_state)
                for c, qty in eff_inv.items():
                    inventory[(d_id, c)] = float(qty)

            # Cheap pre-filter (does every known route for this village cross a
            # blocked edge?) followed by a live re-route confirmation on the
            # current post-hazard graph G — rather than trusting only the
            # static seeded path list, which never reflects a route that's
            # actually still passable. Fallback-option computation for
            # confirmed-isolated villages happens after the LP call below, so
            # it can be seeded from the LP's actual per-commodity shortfall.
            village_isolation: Dict[str, bool] = {}
            for vil in villages:
                v_id = vil["id"]
                v_routes = [r for r in all_routes if r.get("village_id") == v_id]
                if not v_routes:
                    continue
                b_count = count_blocked_routes(v_id, all_routes, blocked_edges)
                if b_count != len(v_routes):
                    continue
                still_reachable = False
                for r in v_routes:
                    src = r.get("depot_node") or (r.get("path") or [None])[0]
                    tgt = r.get("village_node") or (r.get("path") or [None])[-1]
                    if not src or not tgt:
                        continue
                    try:
                        live_result = risk_aware_dijkstra(G, str(src), str(tgt), min_survivability=0.85)
                        if live_result.path and live_result.feasible:
                            still_reachable = True
                            break
                    except Exception as e:
                        logger.warning(f"Live isolation re-check failed for {v_id}: {e}")
                village_isolation[v_id] = not still_reachable

            from ml.pipeline.resilience import haversine_distance, calculate_village_state
            for vil in villages:
                v_id = vil["id"]
                current_state = vil.get("village_state", "NORMAL")
                hazard_dist = float('inf')
                
                if "lat" in vil and "lon" in vil:
                    hazard_dist = haversine_distance(req.lat, req.lon, vil["lat"], vil["lon"])
                
                stockout_risk = 0.9 if vil.get("inventory_level", 100) < 20 else 0.2
                
                new_state_enum = calculate_village_state(
                    v_id, all_routes, blocked_edges, hazard_dist, stockout_risk, current_state,
                    isolated_override=village_isolation.get(v_id),
                )
                new_state = new_state_enum.name
                
                if new_state != current_state:
                    await db.villages.update_one({"id": v_id}, {"$set": {"village_state": new_state}})
                    
                    if new_state == "EVACUATION_REVIEW":
                        await manager.broadcast({
                            "event": "evacuation_alert",
                            "village_id": v_id,
                            "recommendation": "Evacuation Recommended by AI",
                            "status": new_state
                        })
                        await manager.broadcast({
                            "event": "cascading_reroute",
                            "village_id": v_id,
                            "downstream_preposition": True
                        })
                    elif new_state == "ISOLATED":
                        # Handled above, but we can keep the logic clean
                        pass

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

            # Villages confirmed isolated (see village_isolation above): rank
            # multi-modal fallback delivery (track/drone/helicopter) per
            # commodity, seeded from the LP's actual shortfall so a mode isn't
            # recommended for a commodity the LP could still serve some other way.
            from ml.pipeline.multimodal_fallback import rank_fallback_options
            depot_by_id = {d["id"]: d for d in depots}
            village_by_id = {v["id"]: v for v in villages}
            track_graph = _get_track_graph()
            elevation_lookup = _get_elevation_lookup()
            helipad_list = _get_helipads()
            shortfall = (allocation_out or {}).get("shortfall", {}) or {}

            for v_id, is_isolated in village_isolation.items():
                if not is_isolated:
                    continue
                vil = village_by_id.get(v_id)
                if not vil or "lat" not in vil or "lon" not in vil:
                    continue
                depot_id_for_village = next(
                    (r.get("depot_id") for r in all_routes if r.get("village_id") == v_id), None
                )
                depot = depot_by_id.get(depot_id_for_village)
                if not depot or "lat" not in depot or "lon" not in depot:
                    continue

                fallback_options = {}
                fallback_routes = []
                for c in commodities:
                    qty = shortfall.get(f"{v_id}|{c}") or (vil.get("demand") or {}).get(c, 0)
                    if not qty or qty <= 0:
                        continue
                    ranked = rank_fallback_options(depot, vil, c, qty, track_graph, elevation_lookup, helipad_list)
                    fallback_options[c] = ranked
                    for opt in ranked["ranked"]:
                        if opt["feasible"] and opt["geometry"]:
                            fallback_routes.append({
                                "mode": opt["mode"], "geometry": opt["geometry"],
                                "village_id": v_id, "commodity": c,
                            })

                pop = vil.get("population", 1000)
                weighted_commodities = {c: calculate_weighted_priority(c, pop, 24.0, 0.8) for c in commodities}
                await manager.broadcast({
                    "event": "village_isolated",
                    "village_id": v_id,
                    "status": "ISOLATED",
                    "weighted_commodities": weighted_commodities,
                    "fallback_options": fallback_options,
                    "fallback_routes": fallback_routes,
                })
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

    commodity_routes = []
    if allocation_out and "allocations" in allocation_out:
        from shapely.ops import linemerge
        from ml.pipeline.resilience import COMMODITY_COLORS
        for key, qty in allocation_out["allocations"].items():
            if qty <= 0: continue
            try:
                parts = key.split("|")
                if len(parts) == 3:
                    d_id, v_id, comm = parts
                else:
                    import ast
                    tup = ast.literal_eval(key)
                    if len(tup) == 3:
                        d_id, v_id, comm = tup
                    else:
                        continue
                
                depot_doc = next((d for d in depots if d["id"] == d_id), None)
                village_doc = next((v for v in (village_docs or villages) if v.get("id") == v_id), None)
                if not depot_doc or not village_doc: continue
                d_lat, d_lon = depot_doc.get("lat"), depot_doc.get("lon")
                v_lat, v_lon = village_doc.get("lat"), village_doc.get("lon")
                if d_lat is None or v_lat is None: continue
                
                s_match = _find_nearest_edge_meta(d_lat, d_lon, max_distance_m=5000)
                t_match = _find_nearest_edge_meta(v_lat, v_lon, max_distance_m=5000)
                if not s_match or not t_match:
                    continue
                s_node = str(s_match.get("u") or s_match.get("v"))
                t_node = str(t_match.get("u") or t_match.get("v"))
                r_best = risk_aware_dijkstra(G, s_node, t_node)
                
                if r_best and r_best.path:
                    roads = _get_roads()
                    path_edges = []
                    for i in range(len(r_best.path) - 1):
                        u, v = r_best.path[i], r_best.path[i+1]
                        edge_geom = roads[((roads["u"] == u) & (roads["v"] == v)) | ((roads["u"] == v) & (roads["v"] == u))]
                        if not edge_geom.empty:
                            geom = edge_geom.iloc[0].geometry
                            if geom and not geom.is_empty:
                                path_edges.append(geom)
                    if path_edges:
                        merged = linemerge(path_edges)
                        commodity_routes.append({
                            "depot_id": d_id,
                            "village_id": v_id,
                            "commodity": comm,
                            "quantity": qty,
                            "color": COMMODITY_COLORS.get(comm.lower(), "#000000"),
                            "geometry": mapping(merged),
                            "eta_hours": r_best.travel_hours
                        })
            except Exception as e:
                logger.warning(f"Failed to build commodity route for {key}: {e}")

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
        "commodity_routes": commodity_routes,
        "depot_states": depot_states,
        "srlg_warnings": srlg_warnings,
        "information_sources": information_sources,
        "fairness_relaxed": allocation_out.get("fairness_relaxed", False) if allocation_out else False,
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
        "commodity_routes": commodity_routes,
        "depot_states": depot_states,
        "srlg_warnings": srlg_warnings,
        "information_sources": information_sources,
        "fairness_relaxed": allocation_out.get("fairness_relaxed", False) if allocation_out else False,
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
    route_criticality = "normal"
    sole_route_alert = None
    threshold = 0.7

    if matched_edge_id:
        affected_routes = await db.supply_routes.find(
            {"path": matched_edge_id},
            {"_id": 0},
        ).to_list(200)

        # EC1 SOLE ROUTE
        from ml.pipeline.resilience import check_sole_route, RISK_THRESHOLDS
        all_routes = await db.supply_routes.find({"active": {"$ne": False}}, {"_id": 0}).to_list(1000)
        for route in affected_routes:
            vid = route.get("village_id")
            if vid and check_sole_route(vid, all_routes):
                route_criticality = "sole_route"
                threshold = RISK_THRESHOLDS.get("SOLE_ROUTE_THRESHOLD", 0.5)
                sole_route_alert = f"CRITICAL: ONLY route to {vid}. Pre-positioning URGENT."
                break

    pre_positioning_recommended = peak > threshold
    pre_positioning_plan = None
    cost_comparison = None
    last_safe_departure = None

    if pre_positioning_recommended:
        from ml.pipeline.resilience import calculate_last_safe_departure
        closure_time = 2.0 if peak > 0.9 else 6.0
        travel_time = 1.0
        minutes = calculate_last_safe_departure(closure_time, travel_time)
        last_safe_departure = {
            "minutes_remaining": round(minutes),
            "status": "POSSIBLE" if minutes > 0 else "TOO_LATE"
        }

        n_vehicles = max(len(affected_routes), 2)
        commodities = {"food": 80 * n_vehicles, "water": 120 * n_vehicles, "medicine": 40 * n_vehicles, "fuel": 30 * n_vehicles}
        route_hint = affected_routes[0] if affected_routes else {
            "origin": {"lat": req.lat, "lon": req.lon},
            "note": "pre-position to nearest depot covering this coordinate",
        }

        # Replace the flat per-vehicle guess above with a real LP-optimized
        # allocation when we know which village(s) are actually at risk (i.e.
        # the coordinate matched a real supply route). Small problem size
        # (<=5 depots x <=2 villages per commodity) so this stays fast; falls
        # back to the heuristic above on any failure or when nothing matched.
        if affected_routes:
            try:
                from ml.pipeline.preposition_lp import optimize_prepositioning

                def _hav_km(lat1, lon1, lat2, lon2):
                    R = 6371.0
                    p1, p2 = math.radians(lat1), math.radians(lat2)
                    dphi, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
                    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
                    return 2 * R * math.asin(math.sqrt(a))

                village_ids = list({r["village_id"] for r in affected_routes if r.get("village_id")})
                all_depots = await db.depots.find({}, {"_id": 0}).to_list(50)
                at_risk_villages = await db.villages.find({"id": {"$in": village_ids}}, {"_id": 0}).to_list(50)
                depot_ids = [d["id"] for d in all_depots]
                depot_by_id = {d["id"]: d for d in all_depots}
                village_by_id = {v["id"]: v for v in at_risk_villages}

                needed_commodities = set()
                for v in at_risk_villages:
                    needed_commodities.update((v.get("demand") or {}).keys())

                lp_commodities = {}
                for commodity in needed_commodities:
                    demand = {v_id: (village_by_id[v_id].get("demand") or {}).get(commodity, 0) for v_id in village_ids}
                    if sum(demand.values()) <= 0:
                        continue
                    inventory = {d_id: (depot_by_id[d_id].get("inventory") or {}).get(commodity, 0) for d_id in depot_ids}
                    transport_cost = {
                        (d_id, v_id): _hav_km(
                            depot_by_id[d_id]["lat"], depot_by_id[d_id]["lon"],
                            village_by_id[v_id]["lat"], village_by_id[v_id]["lon"],
                        )
                        for d_id in depot_ids for v_id in village_ids
                    }
                    allocation = optimize_prepositioning(depot_ids, village_ids, inventory, demand, transport_cost)
                    qty = round(sum(allocation.values()))
                    if qty > 0:
                        lp_commodities[commodity] = qty

                if lp_commodities:
                    commodities = lp_commodities
            except Exception as e:
                logger.warning(f"Prepositioning LP failed, using heuristic fallback: {e}")

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

    # EC15
    confidence_action = {}
    if peak < 0.3:
        confidence_action = {"action": "MONITOR", "cost_false_positive": 1000, "cost_false_negative": 50000}
    elif peak < 0.5:
        confidence_action = {"action": "PREPARE", "cost_false_positive": 5000, "cost_false_negative": 100000}
    elif peak < 0.7:
        confidence_action = {"action": "PRE_POSITION", "cost_false_positive": 25000, "cost_false_negative": 300000}
    else:
        confidence_action = {"action": "EMERGENCY_DISPATCH", "cost_false_positive": 50000, "cost_false_negative": 1000000}

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
        "route_criticality": route_criticality,
        "sole_route_alert": sole_route_alert,
        "last_safe_departure": last_safe_departure,
        "confidence_action": confidence_action,
    }

    if risk_level in ("high", "critical") or pre_positioning_recommended:
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
            "route_criticality": route_criticality,
            "sole_route_alert": sole_route_alert,
            "last_safe_departure": last_safe_departure,
            "confidence_action": confidence_action,
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


@router.get("/pipeline/villages/{village_id}/fallback-options")
async def get_village_fallback_options(village_id: str):
    """Recompute multi-modal fallback options for an already-isolated village
    on demand — e.g. after a page reload, since the isolation WS event fires
    only once at the moment isolation is detected."""
    from core.database import db
    from ml.pipeline.multimodal_fallback import rank_fallback_options

    vil = await db.villages.find_one({"id": village_id}, {"_id": 0})
    if not vil:
        raise HTTPException(status_code=404, detail="Village not found")
    if vil.get("village_state") != "ISOLATED" and vil.get("village_state") != "CRITICAL":
        raise HTTPException(status_code=400, detail="Village is not currently isolated")
    if "lat" not in vil or "lon" not in vil:
        raise HTTPException(status_code=400, detail="Village has no coordinates")

    route = await db.supply_routes.find_one({"village_id": village_id}, {"_id": 0})
    depot_id = route.get("depot_id") if route else None
    depot = await db.depots.find_one({"id": depot_id}, {"_id": 0}) if depot_id else None
    if not depot or "lat" not in depot or "lon" not in depot:
        raise HTTPException(status_code=404, detail="No depot found for this village")

    track_graph = _get_track_graph()
    elevation_lookup = _get_elevation_lookup()
    helipad_list = _get_helipads()

    fallback_options = {}
    for c, qty in (vil.get("demand") or {}).items():
        if not qty or qty <= 0:
            continue
        fallback_options[c] = rank_fallback_options(depot, vil, c, qty, track_graph, elevation_lookup, helipad_list)

    return {"village_id": village_id, "depot_id": depot_id, "fallback_options": fallback_options}


@router.get("/pipeline/helipads")
async def list_helipads():
    """Real (or, if unavailable, clearly-labeled mock) helipad/aerodrome
    points used for the helicopter fallback mode — for map markers."""
    return _get_helipads()


@router.get("/pipeline/multimodal/status")
async def multimodal_status():
    """Pre-demo sanity check: are the track graph / elevation grid / helipads
    loaded, and are they real data or a mock/synthetic fallback?"""
    track_graph = _get_track_graph()
    elevation_lookup = _get_elevation_lookup()
    helipad_list = _get_helipads()

    elevation_source = "unavailable"
    try:
        df = pd.read_parquet(ELEVATION_GRID_PATH)
        if "source" in df.columns and len(df):
            elevation_source = df["source"].mode().iloc[0]
    except Exception:
        pass

    helipad_sources = sorted({h.get("source", "unknown") for h in helipad_list}) if helipad_list else []

    return {
        "track_graph": {"edges": track_graph.number_of_edges() if track_graph else 0},
        "elevation_grid": {"loaded": elevation_lookup is not None, "source": elevation_source},
        "helipads": {"count": len(helipad_list), "sources": helipad_sources},
    }

@router.post("/pipeline/driver/breakdown")
async def driver_breakdown(vehicle_id: str = Query(...)):
    from core.database import db
    from core.ws import manager
    from ml.pipeline.routing import get_k_feasible_paths_hybrid
    from ml.pipeline.logistics_lp import optimize_allocation
    
    vehicle = await db.vehicles.find_one({"id": vehicle_id})
    if not vehicle:
        return {"error": "Vehicle not found"}
    
    cargo = vehicle.get("cargo") or {}
    
    # Snap to nearest edge to get node
    match = _find_nearest_edge_meta(vehicle.get("lat"), vehicle.get("lon"))
    if not match:
        return {"error": "Vehicle not near any road network."}
        
    src_node = str(match.get("u") or match.get("v"))
    
    # Get villages and demand
    villages = await _docs("villages")
    village_ids = [v["id"] for v in villages if v.get("village_node")]
    
    inventory = {(f"rescue_{vehicle_id}", c): q for c, q in cargo.items()}
    demand = {}
    for vil in villages:
        if vil["id"] not in village_ids: continue
        dem = vil.get("demand") or {}
        for c, qty in dem.items():
            demand[(vil["id"], c)] = float(qty)
            
    # Calculate feasibility and cost
    feasible = {}
    cost = {}
    G = _get_graph()
    
    for vil in villages:
        if vil["id"] not in village_ids: continue
        tgt_node = str(vil.get("village_node") or vil.get("id"))
        try:
            routes = get_k_feasible_paths_hybrid(G, src_node, tgt_node, K=1)
            best = routes[0] if routes else None
            feasible[(f"rescue_{vehicle_id}", vil["id"])] = best.feasible if best else False
            cost[(f"rescue_{vehicle_id}", vil["id"])] = best.travel_hours if best else 999.0
        except Exception:
            feasible[(f"rescue_{vehicle_id}", vil["id"])] = False
            cost[(f"rescue_{vehicle_id}", vil["id"])] = 999.0
            
    commodities = list(cargo.keys())
    
    lp_plan = optimize_allocation(
        [f"rescue_{vehicle_id}"], village_ids, inventory, demand, feasible, cost, commodities
    )

    await manager.broadcast({
        "event": "vehicle_breakdown",
        "vehicle_id": vehicle_id,
        "lat": vehicle.get("lat"),
        "lon": vehicle.get("lon"),
        "cargo": cargo,
        "rescue_plan": lp_plan
    })
    
    # We could assign a new vehicle to this rescue path here.
    return {"status": "success", "message": "Rescue LP triggered", "rescue_inventory": cargo, "plan": lp_plan}