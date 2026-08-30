from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Literal
import os
from pathlib import Path
import geopandas as gpd
from shapely.geometry import Point
import pandas as pd
import logging

router = APIRouter()
logging.basicConfig(level=logging.INFO)


class ManualHazardModel(BaseModel):
    lat: float = Field(..., description="Latitude of the observed landslide/flood")
    lon: float = Field(..., description="Longitude of the observed hazard")
    hazard_type: Literal["landslide", "flood", "road_damage", "closure"] = "landslide"
    severity: Literal["low", "medium", "high"] = "high"
    notes: Optional[str] = None


class ManualRoadClosureModel(BaseModel):
    edge_id: str = Field(..., description="The unique OSM edge ID to close")
    closed: bool = True


# Resolve the parquet path relative to this file so the module works no matter
# what the current working directory is.
#
#   backend/ml/pipeline/admin_override.py  <- __file__
#   backend/ml/pipeline/                  <- parents[0]
#   backend/ml/                            <- parents[1]
#   backend/                               <- parents[2]
#   backend/data/processed/roads.parquet
#
# Override with the ROADS_PARQUET env var if you ever need a different file.
_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
ROADS_PARQUET = os.environ.get("ROADS_PARQUET", str(_DATA_DIR / "roads.parquet"))

# Load road network for spatial matching (in production, cache this in memory).
ROADS_GDF = gpd.read_parquet(ROADS_PARQUET)


# NOTE: paths are `/admin/...` (no leading `/api`) because server.py mounts this
# router with prefix="/api". Final URLs become /api/admin/manual-hazard etc.
@router.post("/admin/manual-hazard")
async def ingest_manual_hazard(hazard: ManualHazardModel):
    """
    Allows a government official to drop a pin on the dashboard.
    The system matches the coordinate to the nearest road segment and injects it
    as a hazard, triggering the match_events_roads pipeline.
    """
    try:
        pt_gdf = gpd.GeoDataFrame(
            [{"geometry": Point(hazard.lon, hazard.lat)}],
            crs="EPSG:4326"
        ).to_crs(ROADS_GDF.crs)

        nearest_roads = gpd.sjoin_nearest(
            pt_gdf,
            ROADS_GDF[["edge_id", "geometry"]],
            how="left",
            max_distance=500
        )

        if nearest_roads.empty or pd.isna(nearest_roads.iloc[0].get("edge_id")):
            raise HTTPException(
                status_code=404,
                detail="No road found within 500m of the provided coordinates."
            )

        affected_edge_id = nearest_roads.iloc[0]["edge_id"]

        severity_map = {"low": 0.4, "medium": 0.7, "high": 0.95}
        clearance_map = {"low": 2.0, "medium": 6.0, "high": 12.0}

        manual_event = {
            "edge_id": affected_edge_id,
            "hazard_type": hazard.hazard_type,
            "blockage_pct": severity_map[hazard.severity],
            "est_clearance_hrs": clearance_map[hazard.severity],
            "source": "manual_official"
        }

        logging.info(f"Manual hazard injected at edge {affected_edge_id} by official.")

        # Trigger the replanner directly (if imported in the same context).
        try:
            from ml.pipeline.replanner import replanner_instance
            replanner_instance.inject_manual_hazard(manual_event)
        except Exception as e:
            logging.warning(f"Replanner failed to initialize or run (possibly due to empty hazards data): {e}")

        return {
            "status": "success",
            "message": "Hazard matched to road network and injected.",
            "matched_edge_id": affected_edge_id,
            "hazard_data": manual_event
        }

    except HTTPException:
        raise  # propagate FastAPI HTTPExceptions unchanged
    except Exception as e:
        logging.error(f"Failed to process manual hazard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# NOTE: same as above — no leading /api here.
@router.post("/admin/close-road")
async def manually_close_road(closure: ManualRoadClosureModel):
    """Directly closes a specific road edge by ID."""
    logging.info(f"Manual closure executed on edge {closure.edge_id}")
    return {"status": "success", "edge_id": closure.edge_id, "closed": closure.closed}