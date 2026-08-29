import math
import heapq
import networkx as nx
from dataclasses import dataclass
from typing import List, Dict, Any

# Import the new hybrid engine
from ml.pipeline.hybrid_routing_engine import HybridRoutingEngine, OlaMapsTrafficClient

@dataclass
class RouteResult:
    path: list
    travel_hours: float
    survivability: float
    expected_risk: float
    feasible: bool

def edge_survival(edge_data: Dict[str, Any], arrival_hours: float) -> float:
    """Calculates edge survival using Sigmoid decay."""
    p0 = float(edge_data.get("block_probability", 0.0))
    if p0 <= 0:
        return 1.0
    clearance = max(float(edge_data.get("reopen_after_hours", 6.0)), 1e-3)
    decay = 1.0 / (1.0 + math.exp(6.0 * (arrival_hours - clearance) / clearance))
    p_t = p0 * decay
    return 1.0 - min(p_t, 0.99)

def evaluate_time_dependent_path(G: nx.DiGraph, path: list) -> tuple:
    """Evaluates a path for time-dependent wait times and cumulative survivability."""
    elapsed_hours = 0.0
    cumulative_survivability = 1.0
    for u, v in zip(path[:-1], path[1:]):
        edge_data = G.edges[u, v]
        travel_time = float(edge_data.get("travel_hours", 1.0))
        wait_time = 0.0
        if edge_data.get("closed", False):
            reopen_at = float(edge_data.get("reopen_after_hours", 0.0))
            if elapsed_hours < reopen_at:
                wait_time = reopen_at - elapsed_hours
        arrival_at_edge = elapsed_hours + wait_time
        s = edge_survival(edge_data, arrival_at_edge)
        cumulative_survivability *= s
        elapsed_hours = arrival_at_edge + travel_time
        if cumulative_survivability <= 0:
            break
    return elapsed_hours, cumulative_survivability

def build_graph(roads) -> nx.DiGraph:
    """
    Converts a processed DataFrame of roads into a NetworkX DiGraph.
    Nodes are populated with coordinates and elevations for A* / Topo calculations.
    """
    G = nx.DiGraph()
    for _, r in roads.iterrows():
        # Add nodes with coordinates for A* heuristic
        G.add_node(r["u"], x=r.get("x_u", 0.0), y=r.get("y_u", 0.0), elevation=r.get("elevation_u", 0.0))
        G.add_node(r["v"], x=r.get("x_v", 0.0), y=r.get("y_v", 0.0), elevation=r.get("elevation_v", 0.0))
        
        d = {
            "road_id": str(r.get("road_id", "")),
            "travel_hours": float(r.get("travel_time_min", 60)) / 60.0,
            "length_km": float(r.get("length_km", 1.0)),
            "speed_kmph": float(r.get("speed_kmph", 30.0)),
            "elevation_u": float(r.get("elevation_u", 0.0)),
            "elevation_v": float(r.get("elevation_v", 0.0)),
            "block_probability": float(r.get("block_probability", 0)),
            "risk_growth_per_hour": float(r.get("risk_growth_per_hour", 0)),
            "closed": bool(r.get("closed", False)),
            "reopen_after_hours": float(r.get("reopen_after_hours", 0)),
        }
        G.add_edge(r["u"], r["v"], **d)
        if bool(r.get("bidirectional", True)):
            G.add_edge(r["v"], r["u"], **d)
    return G

def get_k_feasible_paths_hybrid(G: nx.DiGraph, source: str, target: str, K: int = 3, min_survivability: float = 0.85) -> List[RouteResult]:
    """
    Uses the HybridRoutingEngine (A* + Topo + Ola Maps) to find the optimal path.
    """
    traffic_client = OlaMapsTrafficClient(api_key="YOUR_OLA_API_KEY")
    engine = HybridRoutingEngine(G, traffic_client)
    
    result = engine.find_optimal_path(source, target, min_survivability)
    
    if result.travel_hours == float("inf"):
        return []
        
    return [RouteResult(
        path=result.path,
        travel_hours=result.travel_hours,
        survivability=result.survivability,
        expected_risk=1.0 - result.survivability,
        feasible=result.survivability >= min_survivability
    )]

def risk_aware_dijkstra(G: nx.DiGraph, source: str, target: str, min_survivability: float = 0.85, risk_weight: float = 4.0) -> RouteResult:
    """Fallback single-path Dijkstra."""
    if source == target:
        return RouteResult([source], 0.0, 1.0, 0.0, True)
    pq = [(0.0, 1.0, 0.0, source, [source])]
    best = {}
    while pq:
        cost, surv, elapsed, u, path = heapq.heappop(pq)
        key = (u, round(surv, 3))
        if key in best and best[key] <= cost:
            continue
        best[key] = cost
        if u == target:
            return RouteResult(path, elapsed, surv, 1.0 - surv, surv >= min_survivability)
        for v, data in G[u].items():
            t = float(data.get("travel_hours", 1.0))
            wait = 0.0
            if data.get("closed", False):
                wait = max(0.0, float(data.get("reopen_after_hours", 0.0)) - elapsed)
            arrival = elapsed + wait
            s = edge_survival(data, arrival)
            ns = surv * s
            if ns < min_survivability:
                continue
            ne = arrival + t
            nc = cost + t + wait + risk_weight * (-math.log(max(s, 1e-6)))
            heapq.heappush(pq, (nc, ns, ne, v, path + [v]))
    return RouteResult([], float("inf"), 0.0, 1.0, False)