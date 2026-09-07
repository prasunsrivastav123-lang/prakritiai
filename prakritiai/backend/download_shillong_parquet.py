import osmnx as ox
import pandas as pd
import geopandas as gpd

def download_shillong_parquet():
    # Shillong GPS Coordinates
    lat, lon = 25.5788, 91.8933
    
    print("Downloading all roads and trails within 10km of Shillong...")
    
    # Download 10km radius
    G = ox.graph_from_point((lat, lon), dist=10000, network_type='all')
    
    # Convert the Graph into GeoPandas DataFrames
    nodes, edges = ox.graph_to_gdfs(G)
    
    print(f"Download complete! Found {len(edges)} road segments.")
    
    # Cleanup: Parquet doesn't like Python lists inside columns. 
    # OSMNX sometimes puts lists in columns like 'highway' or 'name' if roads merge.
    # We must convert all list/dict columns to strings before saving.
    for col in edges.columns:
        if edges[col].apply(lambda x: isinstance(x, (list, dict))).any():
            edges[col] = edges[col].astype(str)
            
    # Save directly to Parquet
    filepath = "shillong_10km_edges.parquet"
    edges.to_parquet(filepath)
    
    print(f"Success! Saved geometrically accurate road edges to: {filepath}")

if __name__ == "__main__":
    download_shillong_parquet()
