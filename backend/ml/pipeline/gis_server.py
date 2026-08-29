import fastapi
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import geopandas as gpd
import pandas as pd
import json
from shapely.geometry import Point, LineString
from typing import Dict, Any, List
import logging
from confluent_kafka import Producer
from pydantic import BaseModel

# Import routers and routing engine
from ml.pipeline.admin_override import router as admin_router
from ml.pipeline.routing import build_graph, get_k_feasible_paths_hybrid

app = FastAPI(title="NER Logistics Intelligence GIS Server")

# Enable CORS for frontend dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include admin override endpoints (Manual hazard injection)
app.include_router(admin_router)

logging.basicConfig(level=logging.INFO)

# Initialize Kafka Producer for forwarding bulk field reports
kafka_producer = Producer({'bootstrap.servers': 'localhost:9092'})

# Load graph at startup (Ensure this points to the correct parquet file)
ROADS_DF = pd.read_parquet("data/processed/roads.parquet")
G = build_graph(ROADS_DF)

# Pydantic model for receiving bulk reports
class ReportPayload(BaseModel):
    reports: List[Dict[str, Any]]

@app.get("/health")
@app.get("/api/health")
def health_check():
    """Lightweight endpoint for mobile app network reachability checks."""
    return {"status": "online"}

@app.get("/api/routes/live-reroute")
def live_reroute_driver(current_node: str = Query(..., description="OSM Node ID where driver is located"), 
                        target_village: str = Query(..., description="OSM Node ID of destination")):
    """
    Scenario 2: Dynamic GPS routing. 
    Driver app pings this endpoint. It calculates the optimal A* path using live 
    Ola Maps traffic and returns updated turn-by-turn GeoJSON coordinates.
    """
    # FIX: Cast string inputs from URL to integers to match the graph node data types
    try:
        source_node = int(current_node)
        target_node = int(target_village)
    except ValueError:
        raise HTTPException(status_code=400, detail="Node IDs must be valid integers.")
        
    routes = get_k_feasible_paths_hybrid(G, source_node, target_node)
    
    if not routes:
        raise HTTPException(status_code=404, detail="No feasible path found. Road may be completely blocked.")
        
    best_route = routes[0]
    
    # Convert node path to coordinate array for frontend map rendering
    coords = [[G.nodes[nid].get('x', 0.0), G.nodes[nid].get('y', 0.0)] for nid in best_route.path]
    
    return {
        "status": "success",
        "routing_mode": "dynamic_traffic",
        "travel_hours": best_route.travel_hours,
        "geometry": {
            "type": "LineString",
            "coordinates": coords
        }
    }

def delivery_report(err, msg):
    """Kafka delivery callback."""
    if err is not None:
        logging.error(f"Kafka message delivery failed: {err}")

@app.post("/api/field-reports/batch")
def receive_bulk_field_reports(payload: ReportPayload):
    """
    Receives BULK offline reports from the field app when network is restored.
    Forwards each report to the Kafka topic to trigger real-time replanning.
    """
    reports = payload.reports
    logging.info(f"Received bulk batch of {len(reports)} field reports.")
    
    for report in reports:
        try:
            # Convert to format expected by the Replanner
            event = {
                "lat": report.get("lat"),
                "lon": report.get("lon"),
                "event_type": report.get("report_type"),
                "blockage_pct": 0.95 if report.get("report_type") == "landslide" else 0.80,
                "est_clearance_hrs": 8.0,
                "source": "field_worker_offline_sync"
            }
            
            # Push to Kafka
            kafka_producer.produce(
                'ml-events', 
                key=str(report.get("id")), 
                value=json.dumps(event).encode('utf-8'),
                callback=delivery_report
            )
            
        except Exception as e:
            logging.error(f"Failed to process field report {report.get('id')}: {e}")
            
    # Flush producer to ensure all messages are sent in this request cycle
    kafka_producer.flush()
    
    return {"status": "success", "processed": len(reports), "forwarded_to_kafka": True}

# --- Mock Map Endpoints for Dashboard UI ---

@app.get("/api/map/roads")
def get_roads():
    mock = gpd.GeoDataFrame({'edge_id': ['r1'], 'status': ['clear'], 'geometry': [LineString([(90, 25), (91, 26)])]}, crs="EPSG:4326")
    return json.loads(mock.to_json())

@app.get("/api/map/hazards")
def get_hazards():
    mock = gpd.GeoDataFrame({'hazard_id': ['h1'], 'type': ['landslide'], 'geometry': [Point(91.5, 26.5)]}, crs="EPSG:4326")
    return json.loads(mock.to_json())

@app.get("/api/analytics/district-status")
def get_district_status(district: str = Query(..., description="e.g., Dima Hasao")):
    return {
        "district": district,
        "overall_connectivity": "Degraded",
        "accessible_villages": 42,
        "inaccessible_villages": 3,
        "active_supply_routes": 5,
        "unmet_demand": {
            "medicine": 0,
            "food": 120,
            "materials": 500
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)