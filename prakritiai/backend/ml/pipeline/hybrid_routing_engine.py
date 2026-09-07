import math
import heapq
import networkx as nx
import requests
from typing import Optional, Dict, Tuple, List, Any
from dataclasses import dataclass
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

@dataclass
class HybridRouteResult:
    path: List[str]
    travel_hours: float
    total_distance_km: float
    routing_mode: str  # "live_traffic" or "topo_fallback"
    survivability: float

class OlaMapsTrafficClient:
    """Client for fetching live traffic telemetry from Ola Maps API."""
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.cache: Dict[str, float] = {}
        self.timeout = 2.0  # Strict 2-second timeout for resilience

    def get_live_speed(self, edge_id: str, u_coords: Tuple[float, float], v_coords: Tuple[float, float]) -> Optional[float]:
        if edge_id in self.cache:
            return self.cache[edge_id]
        try:
            # Mock API Call to Ola Maps
            raise requests.exceptions.Timeout("Ola Maps API timed out.")
        except requests.exceptions.RequestException:
            return None

class HybridRoutingEngine:
    """Integrates OSM, topographical elevation, and live traffic into an A* traversal."""
    
    def __init__(self, G: nx.DiGraph, traffic_client: Optional[OlaMapsTrafficClient] = None):
        self.G = G
        self.traffic_client = traffic_client
        self.max_speed_kmph = 80.0  # Max road speed for A* heuristic
        self.node_coords = {n: (data.get('x', 0), data.get('y', 0)) for n, data in G.nodes(data=True)}

    def calculate_topo_speed(self, v_base: float, slope: float, k: float = 0.05) -> float:
        """v_topo = v_base * exp(-k * max(0, slope))"""
        penalty = math.exp(-k * max(0.0, slope))
        return v_base * penalty

    def calculate_slope(self, elev_u: float, elev_v: float, length_m: float) -> float:
        if length_m == 0: return 0.0
        return (elev_v - elev_u) / length_m

    def haversine_distance(self, coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
        lon1, lat1 = coord1
        lon2, lat2 = coord2
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    def a_star_heuristic(self, node: str, target: str) -> float:
        if node not in self.node_coords or target not in self.node_coords:
            return 0.0
        dist_km = self.haversine_distance(self.node_coords[node], self.node_coords[target])
        return dist_km / self.max_speed_kmph

    def evaluate_edge_weight(self, u: str, v: str, edge_data: Dict[str, Any]) -> Tuple[float, str]:
        length_km = float(edge_data.get("length_km", 1.0))
        v_base = float(edge_data.get("speed_kmph", 30.0))
        
        # 1. Try Live Traffic Telemetry
        if self.traffic_client:
            u_coord = self.node_coords.get(u)
            v_coord = self.node_coords.get(v)
            if u_coord and v_coord:
                live_speed = self.traffic_client.get_live_speed(edge_data.get("road_id"), u_coord, v_coord)
                if live_speed is not None and live_speed > 0:
                    travel_hours = length_km / live_speed
                    return travel_hours, "live_traffic"
        
        # 2. Fallback to Topographical Speed Penalty
        elev_u = float(edge_data.get("elevation_u", 0.0))
        elev_v = float(edge_data.get("elevation_v", 0.0))
        length_m = length_km * 1000.0
        slope = self.calculate_slope(elev_u, elev_v, length_m)
        v_topo = self.calculate_topo_speed(v_base, slope)
        
        travel_hours = length_km / max(v_topo, 5.0)
        return travel_hours, "topo_fallback"

    def find_optimal_path(self, source: str, target: str, min_survivability: float = 0.85) -> HybridRouteResult:
        if source not in self.G or target not in self.G:
            return HybridRouteResult([], float("inf"), 0, "error", 0.0)

        pq = [(self.a_star_heuristic(source, target), 0.0, 1.0, source, [source], [])]
        visited = set()
        
        while pq:
            f, g, surv, u, path, modes = heapq.heappop(pq)
            if u == target:
                total_dist = sum(self.G.edges[path[i], path[i+1]].get("length_km", 0) for i in range(len(path)-1))
                final_mode = "live_traffic" if "live_traffic" in modes else "topo_fallback"
                return HybridRouteResult(path, g, total_dist, final_mode, surv)
                
            if u in visited: continue
            visited.add(u)
            
            for v, edge_data in self.G[u].items():
                if v in visited: continue
                    
                travel_hours, mode = self.evaluate_edge_weight(u, v, edge_data)
                
                # Calculate Risk / Survivability
                p0 = float(edge_data.get("block_probability", 0.0))
                clearance = max(float(edge_data.get("reopen_after_hours", 6.0)), 1e-3)
                # Clamp: a search exploring a long detour can reach very large
                # g (elapsed hours); math.exp overflows well before that.
                exponent = max(-700.0, min(700.0, 6.0 * (g - clearance) / clearance))
                decay = 1.0 / (1.0 + math.exp(exponent))
                p_t = p0 * decay
                edge_survival = 1.0 - min(p_t, 0.99)
                
                new_surv = surv * edge_survival
                if new_surv < min_survivability: continue
                    
                new_g = g + travel_hours
                new_f = new_g + self.a_star_heuristic(v, target)
                heapq.heappush(pq, (new_f, new_g, new_surv, v, path + [v], modes + [mode]))
                
        return HybridRouteResult([], float("inf"), 0, "no_path", 0.0)