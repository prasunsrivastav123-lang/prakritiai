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
from shapely.geometry import Point
from fastapi import APIRouter, HTTPException
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
    roads = _get_roads()
    pt = gpd.GeoDataFrame(
        [{"geometry": Point(lon, lat)}],
        crs="EPSG:4326"
    ).to_crs(roads.crs)

    nearest = gpd.sjoin_nearest(
        pt, roads[["edge_id", "geometry"]],
        how="left", max_distance=5000
    )

    if nearest.empty or pd.isna(nearest.iloc[0].get("edge_id")):
        raise HTTPException(
            status_code=404,
            detail=f"No road found within 5km of ({lat}, {lon})"
        )

    return str(nearest.iloc[0]["edge_id"])


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