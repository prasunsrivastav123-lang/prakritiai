# test_sync.py
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from ml.pipeline.offline_sync_engine import OfflineSyncEngine

# FIX: Add /api to the server_url
engine = OfflineSyncEngine(server_url="http://localhost:8000/api")

print("1. Simulating offline report save...")
engine.save_report_offline(
    lat=25.5788, 
    lon=91.8933, 
    report_type="landslide", 
    description="Road blocked near Cherrapunji"
)

print("2. Checking network reachability...")
is_online = engine._check_network_reachable()
print(f"   Network Online: {is_online}")

print("3. Forcing immediate bulk sync...")
success = engine._push_reports()

if success:
    print("✅ SUCCESS: Reports were synced to the server!")
else:
    print("❌ ERROR: Sync failed. Check Uvicorn logs.")