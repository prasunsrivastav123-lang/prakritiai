import math
from enum import Enum, auto
from typing import Dict, List, Any

class VillageState(Enum):
    NORMAL = "NORMAL"
    AT_RISK = "AT_RISK"
    PREPOSITION = "PREPOSITION"
    ISOLATED = "ISOLATED"
    CRITICAL = "CRITICAL"
    EVACUATION_REVIEW = "EVACUATION_REVIEW"
    EVACUATING = "EVACUATING"
    EVACUATED = "EVACUATED"

class DepotState(Enum):
    OPERATIONAL = 1.0
    DEGRADED = 0.5
    PARTIALLY_UNAVAILABLE = 0.2
    UNAVAILABLE = 0.0

class GPSState(Enum):
    TRACKED = "TRACKED"
    GPS_DELAYED = "GPS_DELAYED"
    POSITION_ESTIMATED = "POSITION_ESTIMATED"
    COMMUNICATION_LOST = "COMMUNICATION_LOST"

COMMODITY_CRITICALITY = {
    "medicine": 1.0,
    "food": 0.7,
    "water": 0.5,
    "fuel": 0.3
}

COMMODITY_COLORS = {
    "food": "#16A34A",
    "water": "#2563EB",
    "medicine": "#DC2626",
    "fuel": "#EA580C"
}

HAZARD_PRIORITY = {
    "verified_closure": 5,
    "field_report": 4,
    "satellite": 3,
    "weather": 2,
    "ai_prediction": 1
}

RISK_THRESHOLDS = {
    "SOLE_ROUTE_THRESHOLD": 0.5,
    "DEFAULT_THRESHOLD": 0.7,
    "CRITICAL_THRESHOLD": 0.9
}

SAFETY_BUFFER_MINUTES = 30

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in meters using Haversine formula."""
    R = 6371000 # Radius of Earth in meters
    phi_1 = math.radians(lat1)
    phi_2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi / 2.0)**2 + \
        math.cos(phi_1) * math.cos(phi_2) * math.sin(delta_lambda / 2.0)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def calculate_weighted_priority(commodity: str, population: int, isolation_hours: float, stockout_risk: float) -> float:
    criticality = COMMODITY_CRITICALITY.get(commodity.lower(), 0.5)
    return criticality * population * isolation_hours * stockout_risk

def calculate_last_safe_departure(closure_time: float, travel_time: float, buffer: float = 30) -> float:
    """Returns minutes remaining. closure_time and travel_time are in hours, buffer is in minutes."""
    return (closure_time - travel_time) * 60 - buffer

def check_sole_route(village_id: str, supply_routes: List[Dict[str, Any]]) -> bool:
    """Check if there is only one active route to the village."""
    active_routes = [r for r in supply_routes if r.get('village_id') == village_id and r.get('active', True)]
    return len(active_routes) == 1

def count_blocked_routes(village_id: str, supply_routes: List[Dict[str, Any]], blocked_edges: List[str]) -> int:
    blocked_count = 0
    for route in supply_routes:
        if route.get('village_id') == village_id and route.get('active', True):
            path = route.get('path', [])
            if any(edge in blocked_edges for edge in path):
                blocked_count += 1
    return blocked_count

def calculate_depot_state(depot_id: str, routes: List[Dict[str, Any]], blocked_edges: List[str]) -> DepotState:
    depot_routes = [r for r in routes if r.get('depot_id') == depot_id and r.get('active', True)]
    if not depot_routes:
        return DepotState.OPERATIONAL
    
    blocked_count = 0
    for route in depot_routes:
        path = route.get('path', [])
        if any(edge in blocked_edges for edge in path):
            blocked_count += 1
            
    if blocked_count == 0:
        return DepotState.OPERATIONAL
    elif blocked_count <= 2:
        return DepotState.DEGRADED
    elif blocked_count < len(depot_routes):
        return DepotState.PARTIALLY_UNAVAILABLE
    else:
        return DepotState.UNAVAILABLE

def calculate_effective_inventory(physical_inventory: Dict[str, float], depot_state: DepotState) -> Dict[str, float]:
    factor = depot_state.value
    return {k: v * factor for k, v in physical_inventory.items()}
