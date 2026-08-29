# network/match_events_roads.py
import geopandas as gpd

def match_events_to_roads(roads_path, events_path, out_path="data/processed/events_matched.parquet"):
    print("Loading road network...")
    roads = gpd.read_file(roads_path, layer="lines")
    valid_highways = ["motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential"]
    roads = roads[roads["highway"].isin(valid_highways)].copy()
    roads["edge_id"] = roads.get("osm_id", roads.index.astype(str))

    print("Loading disaster events from AI model...")
    events = gpd.read_file(events_path)

    # Reproject to meters (UTM Zone 46N for NER)
    roads_m = roads.to_crs(32646)
    events_m = events.to_crs(32646)

    print("Buffering events and finding affected roads...")
    events_buffered = events_m.copy()
    events_buffered["geometry"] = events_buffered.geometry.buffer(500)

    # FIX: Explicitly keep AI columns so they aren't lost in the sjoin
    ai_columns = [c for c in ["blockage_pct", "est_clearance_hrs", "risk_growth_per_hour", "hazard_type"] if c in events_buffered.columns]
    roads_subset = roads_m[["edge_id", "geometry"]]

    joined = gpd.sjoin(events_buffered, roads_subset, how="inner", predicate="intersects")
    
    # Ensure the AI columns are retained in the final output
    cols_to_save = ai_columns + ["edge_id", "index_right"]
    joined[cols_to_save].to_parquet(out_path)
    print(f"Done! Saved matched events to {out_path}")