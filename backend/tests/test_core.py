# test_core.py
import pandas as pd
from ml.pipeline.orchestrator import disaster_response_orchestrator

# 1. Load the graph you just built
roads_df = pd.read_parquet("data/processed/roads.parquet")

# 2. Pick a connected u and v from the SAME edge to guarantee they are connected
# Do NOT cast to str, keep the original data type (int64)
depot_node = roads_df.iloc[0]["u"]
village_node = roads_df.iloc[0]["v"]

# 3. Define test data
depots = [depot_node]
villages = [village_node]
inventory = {(depot_node, "medicine"): 100, (depot_node, "food"): 100}
demand = {(village_node, "medicine"): 50, (village_node, "food"): 50}
commodities = ["medicine", "food"]

# 4. Mock a hazard with LOW probability (10% blocked)
# Survivability will be ~0.90, which is above the 0.85 threshold, so it's feasible!
hazards_df = pd.DataFrame([{
    "edge_id": roads_df.iloc[0]["edge_id"],
    "blockage_pct": 0.10,  
    "est_clearance_hrs": 4.0,
    "risk_growth_per_hour": 0.0
}])

print(f"Testing route from Depot {depot_node} to Village {village_node}...")
print("Running Orchestrator...")
result = disaster_response_orchestrator(depots, villages, inventory, demand, roads_df, hazards_df, commodities)

print("\n--- ALLOCATIONS ---")
print(result["allocations"])
print("\n--- SHORTFALLS ---")
print(result["shortfall"])
print("\n--- ROUTES ---")
for key, path in result["routes"].items():
    print(f"Route from {key[0]} to {key[1]}: {len(path)} nodes traversed")
