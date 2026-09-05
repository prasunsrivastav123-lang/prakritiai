import osmnx as ox
import os

# USE RUSSIAN OVERPASS MIRROR (Much faster, fewer timeouts)
ox.settings.overpass_endpoint = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
ox.settings.timeout = 1800 # Allow 30 minutes for massive queries

print("Downloading OSM road network for NER pilot area...")
print("Coverage: 90.5E to 95.0E, 23.5N to 26.5N (Meghalaya + Nagaland + Manipur)")

G = ox.graph_from_bbox(
    bbox=(26.5, 23.5, 95.0, 90.5),
    network_type="all",

    simplify=True
)
print(f"Graph: {len(G.nodes)} nodes, {len(G.edges)} edges")

edges = ox.graph_to_gdfs(G, nodes=False)
edges = edges.reset_index()
edges["edge_id"] = edges.index.astype(str)
edges = edges[["edge_id", "geometry", "length", "highway"]]

edges.to_parquet("data/processed/roads.parquet")
size_mb = os.path.getsize("data/processed/roads.parquet") / (1024 * 1024)
print(f"Saved roads.parquet: {len(edges)} edges, {size_mb:.1f} MB")
print(f"Bounds: {edges.total_bounds}")
print("DONE")
