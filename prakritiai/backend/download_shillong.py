import osmnx as ox

def download_shillong_roads():
    # Shillong GPS Coordinates
    lat, lon = 25.5788, 91.8933
    
    print(f"Downloading all roads and trails within 10km of Shillong...")
    
    # dist=10000 means 10,000 meters (10 km)
    # network_type='all' includes walking trails, dirt paths, and highways
    G = ox.graph_from_point((lat, lon), dist=10000, network_type='all')
    
    print(f"Download complete! Found {len(G.edges)} road segments.")
    
    # Save the graph for your A* engine
    filepath = "shillong_10km.graphml"
    ox.save_graphml(G, filepath)
    print(f"Saved successfully to: {filepath}")

if __name__ == "__main__":
    download_shillong_roads()
