import osmnx as ox
import geopandas as gpd
import pandas as pd
import logging
from shapely.geometry import LineString

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SPEEDS = {"motorway":80,"trunk":60,"primary":50,"secondary":40,
          "tertiary":30,"unclassified":25,"residential":15}

def build_multimodal_network(place_query: str, out_path: str = "data/processed/multimodal_roads.parquet"):
    """Builds road network and injects aerial/waterway fallback edges."""
    logging.info(f"Downloading road network for {place_query}...")
    G = ox.graph_from_place(place_query, network_type="drive", simplify=True, retain_all=False)
    
    # Mock Elevation (Replace with actual API)
    for _, data in G.nodes(data=True):
        data['elevation'] = 0.0
        
    nodes, edges = ox.graph_to_gdfs(G)
    edges = edges[edges["highway"].isin(SPEEDS.keys())].copy()
    
    node_data = nodes[['x', 'y', 'elevation']].reset_index().rename(columns={'index': 'osmid'})
    edges = edges.merge(node_data, left_on='u', right_on='osmid', how='left')
    edges = edges.rename(columns={'x': 'x_u', 'y': 'y_u', 'elevation': 'elevation_u'})
    edges = edges.merge(node_data, left_on='v', right_on='osmid', how='left')
    edges = edges.rename(columns={'x': 'x_v', 'y': 'y_v', 'elevation': 'elevation_v'})

    roads = pd.DataFrame({
        "edge_id"   : [f"{u}_{v}_{k}" for u,v,k in edges.index],
        "u"         : edges["u"].values,
        "v"         : edges["v"].values,
        "length_km" : edges["length"].values / 1000.0,
        "highway"   : edges["highway"].apply(lambda h: h[0] if isinstance(h, list) else h),
        "elevation_u": edges["elevation_u"].fillna(0.0).values,
        "elevation_v": edges["elevation_v"].fillna(0.0).values,
        "x_u"       : edges["x_u"].values,
        "y_u"       : edges["y_u"].values,
        "x_v"       : edges["x_v"].values,
        "y_v"       : edges["y_v"].values
    })
    roads["speed_kmph"] = roads["highway"].map(SPEEDS).fillna(25)
    roads["travel_time_min"] = roads["length_km"] / roads["speed_kmph"] * 60
    roads["bidirectional"] = ~roads["highway"].isin(["motorway"])
    roads["road_id"] = roads["edge_id"]
    roads["edge_type"] = "road"               
    roads["operational_cost"] = 1.0           

    # --- INJECT MULTIMODAL EDGES ---
    multimodal_additions = []
    
    # Mock an Aerial Edge (Helicopter) from Depot (Node A) to cut-off Village (Node B)
    # Travels fast (200kmph), immune to landslides (block_prob=0), but costs 100x more.
    if not roads.empty:
        multimodal_additions.append({
            "edge_id": "heli_1", "u": roads.iloc[0]["u"], "v": roads.iloc[-1]["v"],
            "length_km": 50.0, "highway": "aerial", "elevation_u": 0, "elevation_v": 0,
            "x_u": roads.iloc[0]["x_u"], "y_u": roads.iloc[0]["y_u"],
            "x_v": roads.iloc[-1]["x_v"], "y_v": roads.iloc[-1]["y_v"],
            "speed_kmph": 200.0, "travel_time_min": 15.0, "bidirectional": True,
            "road_id": "heli_1", "edge_type": "aerial", "operational_cost": 100.0
        })
    
    full_network = pd.concat([roads, pd.DataFrame(multimodal_additions)], ignore_index=True)
    full_network.to_parquet(out_path)
    logging.info(f"Saved {len(full_network)} multimodal segments.")
    return full_network