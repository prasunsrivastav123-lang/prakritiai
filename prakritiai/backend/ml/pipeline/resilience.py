import math
from enum import Enum, auto
from typing import Dict, List, Any, Optional

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
    "government": 5,
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

def calculate_village_state(
    village_id: str,
    routes: List[Dict[str, Any]],
    blocked_edges: List[str],
    hazard_dist: float = float('inf'),
    stockout_risk: float = 0.0,
    current_state: str = "NORMAL",
    isolated_override: Optional[bool] = None,
) -> VillageState:
    # Manual overrides or active evacuations shouldn't be automatically reverted
    if current_state in ["EVACUATING", "EVACUATED"]:
        return VillageState[current_state]

    # Check isolation. isolated_override lets a caller substitute a live,
    # graph-based feasibility re-check (does any vehicle route still exist on
    # the current post-hazard graph?) instead of trusting the static seeded
    # supply_routes.path list, which never reflects newly-opened alternates.
    if isolated_override is not None:
        isolated = isolated_override
    else:
        village_routes = [r for r in routes if r.get('village_id') == village_id and r.get('active', True)]
        b_count = count_blocked_routes(village_id, routes, blocked_edges)
        isolated = (len(village_routes) > 0 and b_count == len(village_routes))

    if hazard_dist <= 500:
        return VillageState.EVACUATION_REVIEW
    if isolated and stockout_risk > 0.8:
        return VillageState.CRITICAL
    if isolated:
        return VillageState.ISOLATED
    if hazard_dist <= 2000:
        return VillageState.AT_RISK
    
    # If not isolated and hazard far, but current state was EVACUATION_REVIEW? 
    # Usually we leave it for admin to downgrade, but let's allow it to drop to AT_RISK or NORMAL
    return VillageState.NORMAL

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
