"""Government vehicle tracking — locations, dispatch, cargo, and history."""

import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from core.database import db
from core.security import GOVERNMENT_ROLES, get_current_user
from core.ws import manager

router = APIRouter()

GOV_ID_RE = re.compile(r"^[A-Z]{2}-\d{2}-[A-Z]{2}-\d{4}$")
VEHICLE_TYPES = {"truck", "ambulance", "supply_truck", "rescue_vehicle"}
VEHICLE_STATUSES = {"active", "idle", "maintenance", "dispatched", "in_transit"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_id(doc: Optional[dict]) -> Optional[dict]:
    if doc is None:
        return None
    doc.pop("_id", None)
    return doc


async def require_government(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") not in GOVERNMENT_ROLES:
        raise HTTPException(status_code=403, detail="Government role required")
    return user


async def require_government_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") not in {"GOVERNMENT_ADMIN", "SUPER_ADMIN"}:
        raise HTTPException(status_code=403, detail="GOVERNMENT_ADMIN required")
    return user


def _validate_government_id(government_id: str) -> str:
    gid = government_id.strip().upper()
    if not GOV_ID_RE.match(gid):
        raise HTTPException(
            status_code=400,
            detail="government_id must match XX-NN-XX-NNNN (e.g. AS-01-AB-1234)",
        )
    return gid


async def _vehicle_by_gov_id(government_id: str) -> dict:
    gid = government_id.strip().upper()
    v = await db.vehicles.find_one({"government_id": gid}, {"_id": 0})
    if not v:
        v = await db.vehicles.find_one({"government_id": government_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return v


async def _vehicle_by_id(vehicle_id: str) -> dict:
    v = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return v


class RegisterVehicle(BaseModel):
    model_config = ConfigDict(extra="ignore")
    government_id: str
    vehicle_type: str
    department: Optional[str] = None
    lat: float
    lon: float
    driver: Optional[Dict[str, Any]] = None
    status: str = "idle"


class LocationUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    lat: float
    lon: float
    speed: Optional[float] = None
    heading: Optional[float] = None
    status: Optional[str] = None


class DispatchBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    route: Dict[str, Any]
    cargo: Optional[Dict[str, Any]] = None
    destination: Optional[str] = None


class CargoBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    cargo: Dict[str, Any] = Field(..., description="Commodity quantities or cargo metadata")


# ---------------------------------------------------------------------------
# Static paths first (must precede /{vehicle_id})
# ---------------------------------------------------------------------------

@router.get("/track")
async def list_tracked_vehicles(
    status: Optional[str] = None,
    department: Optional[str] = None,
    user: dict = Depends(require_government),
):
    q: Dict[str, Any] = {"government_id": {"$exists": True, "$ne": None}}
    if status:
        q["status"] = status.lower()
    if department:
        q["department"] = department
    return await db.vehicles.find(q, {"_id": 0}).to_list(1000)


@router.get("/track/{government_id}")
async def get_tracked_vehicle(government_id: str, user: dict = Depends(require_government)):
    vehicle = await _vehicle_by_gov_id(government_id)
    history = await db.vehicle_tracking.find(
        {"$or": [
            {"vehicle_id": vehicle["id"]},
            {"government_id": vehicle.get("government_id")},
        ]},
        {"_id": 0},
    ).sort("timestamp", -1).to_list(100)
    return {"vehicle": vehicle, "tracking_history": history}


@router.post("/track/{government_id}/update")
async def update_vehicle_location(
    government_id: str,
    body: LocationUpdate,
    user: dict = Depends(require_government),
):
    vehicle = await _vehicle_by_gov_id(government_id)
    now = _now()
    patch: Dict[str, Any] = {
        "lat": body.lat,
        "lng": body.lon,
        "lon": body.lon,
        "location": {"lat": body.lat, "lon": body.lon},
        "updated_at": now,
        "last_seen_at": now,
    }
    if body.speed is not None:
        patch["speed"] = body.speed
    if body.heading is not None:
        patch["heading"] = body.heading
    if body.status:
        patch["status"] = body.status.lower()

    await db.vehicles.update_one({"id": vehicle["id"]}, {"$set": patch})

    point = {
        "id": str(uuid4()),
        "vehicle_id": vehicle["id"],
        "government_id": vehicle.get("government_id"),
        "lat": body.lat,
        "lon": body.lon,
        "speed": body.speed,
        "heading": body.heading,
        "timestamp": now,
    }
    await db.vehicle_tracking.insert_one({**point})
    point.pop("_id", None)

    payload = {
        "event": "vehicle_location_update",
        "vehicle_id": vehicle["id"],
        "government_id": vehicle.get("government_id"),
        "lat": body.lat,
        "lon": body.lon,
        "speed": body.speed,
        "heading": body.heading,
        "status": patch.get("status", vehicle.get("status")),
        "timestamp": now,
    }
    await manager.broadcast(payload)
    updated = await db.vehicles.find_one({"id": vehicle["id"]}, {"_id": 0})
    return {"status": "ok", "vehicle": updated, "point": point}


@router.post("/register", status_code=201)
async def register_vehicle(body: RegisterVehicle, user: dict = Depends(require_government_admin)):
    gid = _validate_government_id(body.government_id)
    vtype = body.vehicle_type.strip().lower()
    if vtype not in VEHICLE_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid vehicle_type. Valid: {sorted(VEHICLE_TYPES)}")
    if await db.vehicles.find_one({"government_id": gid}):
        raise HTTPException(status_code=400, detail=f"Vehicle {gid} already registered")

    now = _now()
    vehicle = {
        "id": str(uuid4()),
        "government_id": gid,
        "number": gid,
        "vehicle_type": vtype,
        "type": vtype.upper(),
        "department": body.department,
        "lat": body.lat,
        "lng": body.lon,
        "lon": body.lon,
        "location": {"lat": body.lat, "lon": body.lon},
        "heading": 0,
        "speed": 0,
        "status": (body.status or "idle").lower(),
        "destination": "—",
        "eta_minutes": None,
        "cargo": None,
        "assigned_route": None,
        "driver": body.driver,
        "added_by": user.get("email"),
        "created_at": now,
        "updated_at": now,
        "source": "GOVERNMENT",
    }
    await db.vehicles.insert_one({**vehicle})
    vehicle.pop("_id", None)
    await manager.broadcast({
        "event": "vehicle_registered",
        "vehicle_id": vehicle["id"],
        "government_id": gid,
    })
    return vehicle


@router.get("/active")
async def list_active_vehicles(user: dict = Depends(require_government)):
    """Lightweight payload for map markers."""
    q = {
        "government_id": {"$exists": True, "$ne": None},
        "status": {"$in": ["active", "dispatched", "in_transit"]},
    }
    cursor = db.vehicles.find(q, {
        "_id": 0,
        "id": 1,
        "government_id": 1,
        "vehicle_type": 1,
        "type": 1,
        "status": 1,
        "lat": 1,
        "lng": 1,
        "lon": 1,
        "heading": 1,
        "speed": 1,
        "department": 1,
        "destination": 1,
    })
    return await cursor.to_list(1000)


@router.get("/search")
async def search_vehicles(
    government_id: str = Query(..., description="Partial government ID, e.g. AS-01"),
    user: dict = Depends(require_government),
):
    q = government_id.strip()
    if not q:
        return []
    return await db.vehicles.find(
        {"government_id": {"$regex": re.escape(q), "$options": "i"}},
        {"_id": 0},
    ).to_list(100)


@router.post("/{vehicle_id}/dispatch")
async def dispatch_vehicle(
    vehicle_id: str,
    body: DispatchBody,
    user: dict = Depends(require_government),
):
    vehicle = await _vehicle_by_id(vehicle_id)
    now = _now()
    route = dict(body.route or {})
    if body.destination:
        route.setdefault("destination", body.destination)
    patch: Dict[str, Any] = {
        "assigned_route": route,
        "status": "dispatched",
        "destination": body.destination or route.get("destination") or vehicle.get("destination"),
        "dispatched_at": now,
        "updated_at": now,
    }
    if body.cargo is not None:
        patch["cargo"] = body.cargo
        patch["commodity"] = _commodity_from_cargo(body.cargo)
    await db.vehicles.update_one({"id": vehicle_id}, {"$set": patch})
    updated = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    event = {
        "event": "vehicle_dispatched",
        "vehicle_id": vehicle_id,
        "government_id": vehicle.get("government_id"),
        "route": route,
        "cargo": patch.get("cargo", vehicle.get("cargo")),
        "timestamp": now,
    }
    await manager.broadcast(event)
    return {"status": "ok", "vehicle": updated}


@router.post("/{vehicle_id}/recall")
async def recall_vehicle(vehicle_id: str, user: dict = Depends(require_government)):
    vehicle = await _vehicle_by_id(vehicle_id)
    now = _now()
    await db.vehicles.update_one({"id": vehicle_id}, {"$set": {
        "status": "idle",
        "assigned_route": None,
        "destination": "—",
        "eta_minutes": None,
        "recalled_at": now,
        "updated_at": now,
    }})
    updated = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    event = {
        "event": "vehicle_recalled",
        "vehicle_id": vehicle_id,
        "government_id": vehicle.get("government_id"),
        "timestamp": now,
    }
    await manager.broadcast(event)
    return {"status": "ok", "vehicle": updated}


@router.get("/{vehicle_id}/tracking-history")
async def vehicle_tracking_history(
    vehicle_id: str,
    limit: int = Query(50, ge=1, le=500),
    user: dict = Depends(require_government),
):
    await _vehicle_by_id(vehicle_id)
    return await db.vehicle_tracking.find(
        {"vehicle_id": vehicle_id},
        {"_id": 0},
    ).sort("timestamp", -1).to_list(limit)


@router.post("/{vehicle_id}/assign-cargo")
async def assign_cargo(
    vehicle_id: str,
    body: CargoBody,
    user: dict = Depends(require_government),
):
    await _vehicle_by_id(vehicle_id)
    now = _now()
    await db.vehicles.update_one({"id": vehicle_id}, {"$set": {
        "cargo": body.cargo,
        "commodity": _commodity_from_cargo(body.cargo),
        "updated_at": now,
    }})
    updated = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    await manager.broadcast({
        "event": "vehicle_cargo_assigned",
        "vehicle_id": vehicle_id,
        "cargo": body.cargo,
        "timestamp": now,
    })
    return {"status": "ok", "vehicle": updated}


def _commodity_from_cargo(cargo: Any) -> Optional[str]:
    if not isinstance(cargo, dict) or not cargo:
        return None
    if "commodity" in cargo:
        return str(cargo["commodity"]).upper()
    numeric = {k: v for k, v in cargo.items() if isinstance(v, (int, float))}
    if numeric:
        return max(numeric, key=numeric.get).upper()
    return next(iter(cargo.keys())).upper()
