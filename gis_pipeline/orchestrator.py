# orchestrator.py
import logging
import geopandas as gpd
import pandas as pd
from routing.routing import build_graph, get_k_feasible_paths_hybrid
from optimization.logistics_lp import optimize_allocation

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def disaster_response_orchestrator(depots, villages, inventory, demand, roads_df, hazards_df, commodities):
    """
    Main orchestration pipeline. Injects hazards, generates hybrid routes, and solves LP.
    """
    logging.info("Starting orchestrator...")
    
    # Step 1: Inject hazards into the road network
    affected_edges = hazards_df.set_index("edge_id")
    
    # FIX: Initialize default values for all roads to avoid NaN math in A*
    roads_df["block_probability"] = 0.0
    roads_df["closed"] = False
    roads_df["reopen_after_hours"] = 0.0
    roads_df["risk_growth_per_hour"] = 0.0
    
    for idx, row in roads_df.iterrows():
        eid = row["edge_id"]
        if eid in affected_edges.index:
            hazard_data = affected_edges.loc[eid]
            roads_df.at[idx, "block_probability"] = float(hazard_data["blockage_pct"])
            roads_df.at[idx, "closed"] = bool(hazard_data["blockage_pct"] > 0.90)
            roads_df.at[idx, "reopen_after_hours"] = float(hazard_data["est_clearance_hrs"])
            
    # Build the updated NetworkX Graph
    G = build_graph(roads_df)
    
    # Step 2: Generate Feasibility and Cost Matrices using HYBRID A* Engine
    feasible_matrix = {}
    cost_matrix = {}
    best_paths = {}
    
    for depot in depots:
        for village in villages:
            routes = get_k_feasible_paths_hybrid(G, depot, village)
            
            if routes:
                best_route = routes[0] 
                feasible_matrix[(depot, village)] = best_route.feasible
                if best_route.feasible:
                    # Blend hybrid travel time and risk penalty into LP cost
                    cost_matrix[(depot, village)] = best_route.travel_hours + (best_route.expected_risk * 5.0)
                    best_paths[(depot, village)] = best_route.path

    # Step 3: Run the Multi-Commodity LP Allocation
    allocation_plan = optimize_allocation(
        depots, villages, inventory, demand, feasible_matrix, cost_matrix, commodities
    )
    
    return {
        "allocations": allocation_plan.get("allocations", {}),
        "shortfall": allocation_plan.get("shortfall", {}),
        "routes": best_paths
    }