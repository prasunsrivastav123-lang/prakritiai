import urllib.request
import os
from pyrosm import OSM

pbf_url = 'https://download.geofabrik.de/asia/india/north-eastern-zone-latest.osm.pbf'
pbf_file = 'northeast-zone-latest.osm.pbf'
parquet_file = 'data/processed/roads.parquet'

os.makedirs('data/processed', exist_ok=True)

print('1. Downloading raw OSM PBF file from Geofabrik...')
if not os.path.exists(pbf_file):
    urllib.request.urlretrieve(pbf_url, pbf_file)
    print('Download complete!')
else:
    print('PBF file already exists. Skipping download.')

print('2. Initializing pyrosm...')
osm = OSM(pbf_file)

print('3. Parsing network (this is extremely fast)...')
nodes, edges = osm.get_network(network_type='all', nodes=True)

print('4. Formatting dataframe...')
edges = edges.reset_index(drop=True)
if 'id' in edges.columns:
    edges['edge_id'] = edges['id'].astype(str)
else:
    edges['edge_id'] = edges.index.astype(str)

cols_to_keep = ['edge_id', 'geometry', 'length', 'highway']
existing_cols = [c for c in cols_to_keep if c in edges.columns]
edges = edges[existing_cols]

print(f'5. Saving to {parquet_file}...')
edges.to_parquet(parquet_file)

size_mb = os.path.getsize(parquet_file) / (1024 * 1024)
print(f'DONE! Saved {len(edges)} edges. File size: {size_mb:.1f} MB')
