import urllib.request
import os

urls = [
    'https://download.geofabrik.de/asia/india/north-eastern-zone-latest.osm.pbf',
    'https://download.geofabrik.de/asia/india/northeast-zone-latest.osm.pbf',
    'https://download.geofabrik.de/asia/india/eastern-zone-latest.osm.pbf'
]

valid_url = None
for url in urls:
    try:
        req = urllib.request.Request(url, method='HEAD')
        resp = urllib.request.urlopen(req)
        if resp.status == 200:
            valid_url = url
            break
    except:
        pass

if valid_url:
    print(f'Found URL: {valid_url}')
    with open('download_roads_geofabrik.py', 'r') as f:
        content = f.read()
    
    # Replace the bad URL with the good one
    content = content.replace('https://download.geofabrik.de/asia/india/northeast-zone-latest.osm.pbf', valid_url)
    
    with open('download_roads_geofabrik.py', 'w') as f:
        f.write(content)
        
    print('Updated script. Now running it...')
    os.system('python download_roads_geofabrik.py')
else:
    print('Could not find Geofabrik URL.')
