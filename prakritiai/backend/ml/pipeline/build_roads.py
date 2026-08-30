import osmnx as ox
import geopandas as gpd
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SPEEDS = {"motorway":80,"trunk":60,"primary":50,"secondary":40,
          "tertiary":30,"unclassified":25,"residential":15}

def build_canonical_roads(out_path: str = "data/processed/roads.parquet"):
    """Downloads OSM road network via Point+Radius, attaches elevation, saves to parquet."""
    logging.info("Downloading road network around Shillong (5km radius)...")
    center_point = (25.5788, 91.8933)  # Lat, Lon of Shillong
    G = ox.graph_from_point(center_point, dist=5000, network_type="drive", simplify=True, retain_all=False)
    
    # Add elevation (Fallback to 0.0 if API fails, safely disabling topo penalties)
    try:
        G = ox.elevation.add_node_elevations_google(G, api_key="YOUR_ELEVATION_API_KEY")
        G = ox.elevation.add_edge_grades(G, add_absolute=True)
    except Exception as e:
        logging.warning(f"Skipping elevation fetch (Topo penalties disabled): {e}")
        for _, data in G.nodes(data=True):
            data['elevation'] = 0.0
            
    nodes, edges = ox.graph_to_gdfs(G)
    
    # FIX: Reset index so 'u', 'v', and 'key' become standard columns instead of being in the index
    edges = edges.reset_index()
    
    # Filter for valid roads
    edges["highway_type"] = edges["highway"].apply(lambda h: h[0] if isinstance(h, list) else h)
    edges = edges[edges["highway_type"].isin(SPEEDS.keys())].copy()

    # Prepare node data (coordinates and elevations)
    node_data = nodes[['x', 'y', 'elevation']].copy()
    node_data = node_data.reset_index()
    if 'osmid' not in node_data.columns:
        node_data = node_data.rename(columns={node_data.columns[0]: 'osmid'})

    # Merge node data to get u/v coordinates and elevations on edges
    edges = edges.merge(node_data, left_on='u', right_on='osmid', how='left')
    edges = edges.rename(columns={'x': 'x_u', 'y': 'y_u', 'elevation': 'elevation_u'})
    
    edges = edges.merge(node_data, left_on='v', right_on='osmid', how='left')
    edges = edges.rename(columns={'x': 'x_v', 'y': 'y_v', 'elevation': 'elevation_v'})

    # Build final DataFrame
    roads = pd.DataFrame({
        "edge_id"   : [f"{u}_{v}_{k}" for u,v,k in zip(edges["u"], edges["v"], edges["key"])],
        "u"         : edges["u"].values,
        "v"         : edges["v"].values,
        "length_km" : edges["length"].values / 1000.0,
        "highway"   : edges["highway_type"].values,
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
    
    # FIX: Convert to GeoDataFrame so spatial metadata is saved in Parquet
    roads_gdf = gpd.GeoDataFrame(roads, geometry=edges["geometry"].values, crs="EPSG:4326")
    roads_gdf.to_parquet(out_path)
    
    logging.info(f"Saved {len(roads_gdf)} road segments to {out_path}")
    return roads_gdf

if __name__ == "__main__":
    build_canonical_roads()