# network/hazards_aggregate.py
import pandas as pd
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def aggregate_hazards(events_matched_path: str = "data/processed/events_matched.parquet", 
                     out_path: str = "data/processed/hazards.parquet") -> pd.DataFrame:
    """
    Aggregates matched hazard events per edge_id.
    Safely handles missing AI columns and applies default fallback values.
    """
    # 1. Check if the file exists or is empty
    if not os.path.exists(events_matched_path):
        logging.warning(f"File not found: {events_matched_path}. Initializing empty hazards table.")
        agg = pd.DataFrame(columns=["edge_id", "blockage_pct", "est_clearance_hrs", "risk_growth_per_hour"])
        agg.to_parquet(out_path)
        return agg

    em = pd.read_parquet(events_matched_path)
    
    # 2. Handle the case where the AI model found no hazards affecting the road network
    if em.empty:
        logging.info("No active hazard events to aggregate. Creating empty hazards table.")
        agg = pd.DataFrame(columns=["edge_id", "blockage_pct", "est_clearance_hrs", "risk_growth_per_hour"])
        agg.to_parquet(out_path)
        return agg

    # 3. Dynamically build the aggregation dictionary based on available columns
    # This prevents KeyError if the AI model omits a column on a given run
    agg_dict = {}
    if "blockage_pct" in em.columns:
        agg_dict["blockage_pct"] = "max"           # Worst-case blockage wins
    if "est_clearance_hrs" in em.columns:
        agg_dict["est_clearance_hrs"] = "max"      # Slowest clearance wins
    if "risk_growth_per_hour" in em.columns:
        agg_dict["risk_growth_per_hour"] = "sum"   # Accumulate risk growth

    if "edge_id" not in em.columns:
        logging.error("events_matched.parquet is missing 'edge_id' column. Cannot aggregate.")
        raise ValueError("Missing 'edge_id' in matched events.")

    # 4. Perform the groupby aggregation
    if agg_dict:
        agg = em.groupby("edge_id").agg(agg_dict).reset_index()
    else:
        # Fallback if AI model provided NO metric columns, just edge_ids
        agg = em[["edge_id"]].drop_duplicates().copy()
        agg["blockage_pct"] = 0.5   # Default 50% blockage if AI gave no info
        agg["est_clearance_hrs"] = 4.0
        agg["risk_growth_per_hour"] = 0.0

    # 5. Fill any NaNs that might have slipped through the AI model
    # These defaults ensure the routing engine's sigmoid decay math won't break
    if "blockage_pct" in agg.columns:
        agg["blockage_pct"] = agg["blockage_pct"].fillna(0.5) # Assume 50% risk if unknown
    if "est_clearance_hrs" in agg.columns:
        agg["est_clearance_hrs"] = agg["est_clearance_hrs"].fillna(4.0) # Assume 4 hrs to clear if unknown
    if "risk_growth_per_hour" in agg.columns:
        agg["risk_growth_per_hour"] = agg["risk_growth_per_hour"].fillna(0.0)

    # 6. Save the processed hazards file
    agg.to_parquet(out_path)
    logging.info(f"Aggregated {len(agg)} unique road hazards. Saved to {out_path}")
    return agg

if __name__ == "__main__":
    # Example usage hook
    aggregate_hazards()