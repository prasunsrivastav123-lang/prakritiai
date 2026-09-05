import osmnx as ox
import geopandas as gpd
import pandas as pd
import numpy as np
import os, time

# Use alternate Overpass mirrors (the default .de one timed out)
MIRRORS = [
    "https://overpass.kumi.systems/api/interpreter",   # fast mirror
    "https://overpass-api.de/api/interpreter",          # default
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",  # RU mirror
]
ox.settings.overpass_url = MIRRORS[0]
ox.settings.requests_timeout = 300
ox.settings.log_console = True

# Download in 6 smaller chunks (each ~1.5x1.5 degrees — Overpass-friendly)
areas = [
    (26.2, 25.0, 92.3, 90.5, "West Meghalaya (Shillong/Nongstoin)"),
    (26.2, 25.0, 94.5, 92.3, "Central NER (Jowai/Guwahati-east)"),
    (26.5, 25.3, 95.0, 94.3, "East Nagaland (Tuensang/Mokokchung)"),
    (25.3, 24.3, 94.0, 92.3, "Manipur (Imphal/Ukhrul/Senapati)"),
    (25.3, 24.3, 95.0, 94.0, "East Manipur/Nagaland-south"),
    (24.3, 23.5, 93.0, 90.5, "South NER (Aizawl/Agartala)"),
    (24.3, 23.5, 95.0, 93.0, "Mizoram-east/Myanmar border"),
]

all_graphs = []
for north, south, east, west, name in areas:
    print(f"\n=== {name} ===")
    got = False
    for attempt in range(3):
        for mirror in MIRRORS:
            try:
                ox.settings.overpass_url = mirror
                print(f"  Attempt {attempt+1} via {mirror.split('/')[2]}...")
                G = ox.graph_from_bbox(
                    bbox=(north, south, east, west),
                    network_type="drive",
                    simplify=True,
                )
                edges = ox.graph_to_gdfs(G, nodes=False).reset_index()
                all_graphs.append(edges)
                print(f"  OK: {len(edges)} edges")
                got = True
                break
            except Exception as e:
                print(f"  Failed: {str(e)[:80]}")
                time.sleep(5)
        if got:
            break
    if not got:
        print(f"  !! SKIPPED {name} after all retries")

if all_graphs:
    combined = gpd.GeoDataFrame(pd.concat(all_graphs, ignore_index=True), crs=all_graphs[0].crs)
    # Drop duplicates (overlapping chunk borders)
    combined = combined.drop_duplicates(subset=["geometry"]).reset_index(drop=True)
    combined["edge_id"] = combined.index.astype(str)
    combined["length"] = combined["length"].astype(float)

    # Rebuild the columns your pipeline expects
    speed_map = {"motorway": 80, "trunk": 70, "primary": 60, "secondary": 50,
                 "tertiary": 40, "residential": 30, "unclassified": 30}
    combined["highway"] = combined["highway"].astype(str)
    combined["speed_kmph"] = combined["highway"].map(speed_map).fillna(30)
    combined["length_km"] = combined["length"] / 1000.0
    combined["travel_time_min"] = combined["length_km"] / combined["speed_kmph"] * 60.0
    combined["bidirectional"] = True

    # Deterministic bridge tagging for EC5 (SRLG)
    rng = np.random.RandomState(42)
    mask = rng.rand(len(combined)) < 0.05
    bids = rng.randint(1000, 9999, size=len(combined))
    combined["bridge_id"] = None
    combined.loc[mask, "bridge_id"] = [f"bridge_{b}" for b in bids[mask]]

    final = combined[["edge_id", "geometry", "length_km", "highway", "speed_kmph",
                      "travel_time_min", "bidirectional", "bridge_id"]]
    final.to_parquet("data/processed/roads.parquet")
    size_mb = os.path.getsize("data/processed/roads.parquet") / (1024*1024)
    print(f"\n=== DONE ===")
    print(f"Total edges: {len(final)}")
    print(f"File size: {size_mb:.1f} MB")
    print(f"Bounds (W,S,E,N): {final.total_bounds}")
else:
    print("\nERROR: no chunks downloaded — check internet / firewall")
