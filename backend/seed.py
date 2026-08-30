import uuid
from datetime import datetime, timezone

from core.database import db
from core.security import hash_password


def _iso_mins_ago(m: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=m)).isoformat()


from datetime import timedelta  # noqa: E402

# =============================
# Users seed
# =============================

DEMO_ACCOUNTS = [
    {"email": "gov.admin@neris.demo", "password": "Demo@2026", "name": "Aditi Baruah", "role": "GOVERNMENT_ADMIN", "organization": "Government of Assam", "department": "Disaster Management Cell"},
    {"email": "gov.officer@neris.demo", "password": "Demo@2026", "name": "Kiran Deka", "role": "GOVERNMENT_OFFICER", "organization": "State Logistics Authority", "department": "District Ops — Kamrup"},
    {"email": "logistics@neris.demo", "password": "Demo@2026", "name": "NER Logistics Co.", "role": "LOGISTICS_OPERATOR", "organization": "Brahmaputra Freight Pvt Ltd", "department": "Fleet Ops"},
    {"email": "field@neris.demo", "password": "Demo@2026", "name": "R. Marak", "role": "FIELD_OFFICER", "organization": "Field Operations", "department": "West Garo Hills"},
    {"email": "public@neris.demo", "password": "Demo@2026", "name": "Public Access", "role": "PUBLIC_USER", "organization": None, "department": None},
    {"email": "driver@neris.demo", "password": "Demo@2026", "name": "B. Singh", "role": "DRIVER", "organization": "Brahmaputra Freight Pvt Ltd", "department": "Line-haul"},
]


async def _upsert_user(doc: dict):
    import os
    email = doc["email"].strip().lower()
    existing = await db.users.find_one({"email": email})
    payload = {
        "id": existing["id"] if existing else str(uuid.uuid4()),
        "email": email,
        "name": doc["name"],
        "role": doc["role"],
        "organization": doc.get("organization"),
        "department": doc.get("department"),
        "is_active": True,
        "password_hash": hash_password(doc["password"]),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if not existing:
        payload["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.users.insert_one(payload)
    else:
        await db.users.update_one({"email": email}, {"$set": payload})


async def seed_users():
    import os
    await db.users.create_index("email", unique=True)
    await _upsert_user({
        "email": os.environ.get("ADMIN_EMAIL", "aiagency865@gmail.com"),
        "password": os.environ.get("ADMIN_PASSWORD", "Admin@2026"),
        "name": "NERIS Owner",
        "role": "SUPER_ADMIN",
        "organization": "NERIS Platform",
        "department": "Platform Administration",
    })
    for acc in DEMO_ACCOUNTS:
        await _upsert_user(acc)


# =============================
# Dashboard demo dataset (all rows tagged source=DEMO)
# =============================

DEMO_ROADS = [
    {"id": "rd-nh27", "name": "NH-27 Guwahati–Nagaon", "road_class": "highway", "district": "Kamrup Metro", "status": "AT_RISK", "risk": 62, "geometry": {"type": "LineString", "coordinates": [[91.57, 26.12], [91.75, 26.18], [92.05, 26.23], [92.32, 26.30]]}},
    {"id": "rd-nh6", "name": "NH-6 Guwahati–Shillong", "road_class": "highway", "district": "Ri-Bhoi", "status": "BLOCKED", "risk": 91, "geometry": {"type": "LineString", "coordinates": [[91.74, 26.14], [91.65, 25.85], [91.60, 25.57]]}},
    {"id": "rd-nh15", "name": "NH-15 Mangaldai–Tezpur", "road_class": "highway", "district": "Sonitpur", "status": "RESTRICTED", "risk": 55, "geometry": {"type": "LineString", "coordinates": [[92.03, 26.44], [92.35, 26.50], [92.80, 26.63]]}},
    {"id": "rd-nh17", "name": "NH-17 Guwahati–Goalpara", "road_class": "highway", "district": "Goalpara", "status": "OPEN", "risk": 18, "geometry": {"type": "LineString", "coordinates": [[91.74, 26.15], [91.35, 26.10], [90.97, 26.07]]}},
    {"id": "rd-nh715", "name": "NH-715 Tezpur–Jorhat", "road_class": "highway", "district": "Jorhat", "status": "OPEN", "risk": 22, "geometry": {"type": "LineString", "coordinates": [[92.80, 26.63], [93.30, 26.72], [94.20, 26.75]]}},
    {"id": "rd-sh9", "name": "SH-9 Silchar–Aizawl", "road_class": "secondary", "district": "Cachar", "status": "AT_RISK", "risk": 47, "geometry": {"type": "LineString", "coordinates": [[92.78, 24.83], [92.75, 24.20], [92.90, 23.73]]}},
    {"id": "rd-nh29", "name": "NH-29 Dimapur–Kohima", "road_class": "highway", "district": "Kohima", "status": "GOVERNMENT_CLOSED", "risk": 88, "geometry": {"type": "LineString", "coordinates": [[93.73, 25.91], [94.05, 25.70]]}},
    {"id": "rd-nh13", "name": "NH-13 Itanagar–Pasighat", "road_class": "highway", "district": "East Siang", "status": "OPEN", "risk": 15, "geometry": {"type": "LineString", "coordinates": [[93.61, 27.10], [94.30, 27.80], [95.33, 28.06]]}},
    {"id": "rd-nh502", "name": "NH-502 Imphal–Ukhrul", "road_class": "secondary", "district": "Ukhrul", "status": "UNKNOWN", "risk": 40, "geometry": {"type": "LineString", "coordinates": [[93.94, 24.82], [94.35, 24.98]]}},
    {"id": "rd-nh108", "name": "NH-108 Agartala–Udaipur", "road_class": "highway", "district": "Gomati", "status": "OPEN", "risk": 12, "geometry": {"type": "LineString", "coordinates": [[91.28, 23.83], [91.49, 23.53]]}},
    {"id": "rd-nh15w", "name": "NH-15 Guwahati–Mangaldai", "road_class": "highway", "district": "Darrang", "status": "OPEN", "risk": 20, "geometry": {"type": "LineString", "coordinates": [[91.75, 26.18], [91.90, 26.32], [92.03, 26.44]]}},
    {"id": "rd-nh27e", "name": "NH-27 Nagaon–Dimapur", "road_class": "highway", "district": "Karbi Anglong", "status": "OPEN", "risk": 25, "geometry": {"type": "LineString", "coordinates": [[92.32, 26.30], [93.10, 26.05], [93.73, 25.91]]}},
]

DEMO_INCIDENTS = [
    {"id": "NER-20481", "type": "LANDSLIDE", "severity": "CRITICAL", "title": "Landslide Risk", "location": "NH-6, near Sonapur", "lat": 26.07, "lng": 91.63, "source": "AI+GPS", "confidence": 91, "status": "PROVISIONALLY_BLOCKED", "created_minutes_ago": 12},
    {"id": "NER-20479", "type": "FLOOD", "severity": "HIGH", "title": "Flood Probability Rising", "location": "NH-15, Tezpur approach", "lat": 26.55, "lng": 92.55, "source": "AI", "confidence": 78, "status": "UNVERIFIED", "created_minutes_ago": 24},
    {"id": "NER-20477", "type": "TRAFFIC", "severity": "HIGH", "title": "Fleet Anomaly Detected", "location": "NH-27, Baihata stretch — 8 vehicles slowed", "lat": 26.22, "lng": 91.72, "source": "GPS", "confidence": 84, "status": "UNVERIFIED", "created_minutes_ago": 31},
    {"id": "NER-20475", "type": "ROAD_DAMAGE", "severity": "WARNING", "title": "Road Damage Reported", "location": "NH-29, Kohima bypass", "lat": 25.78, "lng": 93.90, "source": "FIELD", "confidence": 72, "status": "VERIFIED", "created_minutes_ago": 47},
    {"id": "NER-20467", "type": "FLOOD", "severity": "HIGH", "title": "River Level Above Threshold", "location": "SH-9, Barak valley", "lat": 24.55, "lng": 92.77, "source": "AI", "confidence": 81, "status": "UNVERIFIED", "created_minutes_ago": 66},
    {"id": "NER-20473", "type": "WEATHER", "severity": "WARNING", "title": "Heavy Rainfall Warning", "location": "Meghalaya hills, NH-6 corridor", "lat": 25.70, "lng": 91.62, "source": "AI", "confidence": 69, "status": "UNVERIFIED", "created_minutes_ago": 58},
    {"id": "NER-20471", "type": "BRIDGE_DAMAGE", "severity": "INFO", "title": "Bridge Inspection Scheduled", "location": "NH-17, Bridge B-17", "lat": 26.10, "lng": 91.35, "source": "GOVERNMENT", "confidence": 100, "status": "VERIFIED", "created_minutes_ago": 132},
    {"id": "NER-20469", "type": "ACCIDENT", "severity": "INFO", "title": "Minor Accident Cleared", "location": "NH-715, near Jorhat", "lat": 26.72, "lng": 93.30, "source": "PUBLIC", "confidence": 55, "status": "RESOLVED", "created_minutes_ago": 188},
]

DEMO_VEHICLES = [
    {"id": "veh-204", "number": "TRK-204", "type": "TRUCK", "lat": 26.19, "lng": 91.80, "heading": 72, "speed": 34, "status": "IN_TRANSIT", "destination": "Nagaon DC", "eta_minutes": 192, "risk": 32, "commodity": "MEDICINE"},
    {"id": "veh-118", "number": "TRK-118", "type": "TRUCK", "lat": 26.46, "lng": 92.30, "heading": 80, "speed": 41, "status": "IN_TRANSIT", "destination": "Tezpur Depot", "eta_minutes": 78, "risk": 55, "commodity": "FOOD"},
    {"id": "veh-332", "number": "LTV-332", "type": "LIGHT", "lat": 26.11, "lng": 91.42, "heading": 262, "speed": 48, "status": "IN_TRANSIT", "destination": "Goalpara", "eta_minutes": 95, "risk": 18, "commodity": "WATER"},
    {"id": "veh-090", "number": "EMG-090", "type": "EMERGENCY", "lat": 26.15, "lng": 91.70, "heading": 190, "speed": 62, "status": "IN_TRANSIT", "destination": "GMCH Guwahati", "eta_minutes": 14, "risk": 12, "commodity": "EMERGENCY_EQUIPMENT"},
    {"id": "veh-451", "number": "TRK-451", "type": "TRUCK", "lat": 26.22, "lng": 91.71, "heading": 75, "speed": 8, "status": "DELAYED", "destination": "Baihata Chariali", "eta_minutes": 240, "risk": 71, "commodity": "FUEL"},
    {"id": "veh-517", "number": "SUV-517", "type": "SUV", "lat": 24.40, "lng": 92.76, "heading": 350, "speed": 29, "status": "IN_TRANSIT", "destination": "Silchar", "eta_minutes": 66, "risk": 47, "commodity": "MEDICINE"},
    {"id": "veh-620", "number": "TRK-620", "type": "TRUCK", "lat": 25.85, "lng": 93.85, "heading": 10, "speed": 0, "status": "DELAYED", "destination": "Kohima", "eta_minutes": 310, "risk": 88, "commodity": "CONSTRUCTION"},
    {"id": "veh-733", "number": "LTV-733", "type": "LIGHT", "lat": 26.68, "lng": 93.10, "heading": 95, "speed": 44, "status": "IN_TRANSIT", "destination": "Jorhat", "eta_minutes": 120, "risk": 22, "commodity": "FOOD"},
    {"id": "veh-842", "number": "2W-842", "type": "TWO_WHEELER", "lat": 27.30, "lng": 94.60, "heading": 40, "speed": 38, "status": "IN_TRANSIT", "destination": "Pasighat", "eta_minutes": 150, "risk": 15, "commodity": "AGRICULTURAL"},
    {"id": "veh-905", "number": "TRK-905", "type": "TRUCK", "lat": 23.70, "lng": 91.40, "heading": 185, "speed": 52, "status": "IN_TRANSIT", "destination": "Udaipur", "eta_minutes": 42, "risk": 12, "commodity": "FOOD"},
    {"id": "veh-011", "number": "SUV-011", "type": "SUV", "lat": 24.90, "lng": 94.10, "heading": 30, "speed": 0, "status": "IDLE", "destination": "—", "eta_minutes": None, "risk": 40, "commodity": None},
    {"id": "veh-156", "number": "EMG-156", "type": "EMERGENCY", "lat": 26.60, "lng": 92.75, "heading": 270, "speed": 55, "status": "IN_TRANSIT", "destination": "Tezpur MC", "eta_minutes": 9, "risk": 55, "commodity": "MEDICINE"},
]

DEMO_VILLAGES = [
    {"id": "vil-majuli", "name": "Majuli Riverine Cluster", "district": "Majuli", "population": 12400, "isolation_risk": "CRITICAL", "days_to_stockout": 2, "primary_commodity": "MEDICINE"},
    {"id": "vil-tuting", "name": "Tuting", "district": "Upper Siang", "population": 3200, "isolation_risk": "CRITICAL", "days_to_stockout": 3, "primary_commodity": "FOOD"},
    {"id": "vil-cherrapunji", "name": "Sohra Outskirts", "district": "East Khasi Hills", "population": 5800, "isolation_risk": "HIGH", "days_to_stockout": 5, "primary_commodity": "FOOD"},
    {"id": "vil-ziro", "name": "Ziro Valley Hamlets", "district": "Lower Subansiri", "population": 9100, "isolation_risk": "MEDIUM", "days_to_stockout": 9, "primary_commodity": "FUEL"},
    {"id": "vil-mon", "name": "Mon Border Villages", "district": "Mon", "population": 7400, "isolation_risk": "HIGH", "days_to_stockout": 6, "primary_commodity": "MEDICINE"},
    {"id": "vil-haflong", "name": "Haflong Periphery", "district": "Dima Hasao", "population": 4200, "isolation_risk": "MEDIUM", "days_to_stockout": 11, "primary_commodity": "FOOD"},
    {"id": "vil-mokokchung", "name": "Mokokchung Rural", "district": "Mokokchung", "population": 11200, "isolation_risk": "LOW", "days_to_stockout": 18, "primary_commodity": "FOOD"},
    {"id": "vil-tezpur", "name": "Tezpur Riverside", "district": "Sonitpur", "population": 15600, "isolation_risk": "LOW", "days_to_stockout": 21, "primary_commodity": "WATER"},
]

DEMO_DELIVERIES = [
    {"id": "DEL-8801", "vehicle": "TRK-204", "origin": "Guwahati", "destination": "Nagaon", "commodity": "MEDICINE", "status": "ON_TRACK", "eta_minutes": 192, "risk": 32, "road": "NH-27"},
    {"id": "DEL-8802", "vehicle": "TRK-118", "origin": "Mangaldai", "destination": "Tezpur", "commodity": "FOOD", "status": "DELAYED", "eta_minutes": 78, "risk": 55, "road": "NH-15"},
    {"id": "DEL-8803", "vehicle": "LTV-332", "origin": "Guwahati", "destination": "Goalpara", "commodity": "WATER", "status": "ON_TRACK", "eta_minutes": 95, "risk": 18, "road": "NH-17"},
    {"id": "DEL-8804", "vehicle": "TRK-451", "origin": "Guwahati", "destination": "Nagaon", "commodity": "FUEL", "status": "AT_RISK", "eta_minutes": 240, "risk": 71, "road": "NH-27"},
    {"id": "DEL-8805", "vehicle": "SUV-517", "origin": "Silchar", "destination": "Aizawl", "commodity": "MEDICINE", "status": "ON_TRACK", "eta_minutes": 66, "risk": 47, "road": "SH-9"},
    {"id": "DEL-8806", "vehicle": "TRK-620", "origin": "Dimapur", "destination": "Kohima", "commodity": "CONSTRUCTION", "status": "DELAYED", "eta_minutes": 310, "risk": 88, "road": "NH-29"},
    {"id": "DEL-8807", "vehicle": "LTV-733", "origin": "Tezpur", "destination": "Jorhat", "commodity": "FOOD", "status": "ON_TRACK", "eta_minutes": 120, "risk": 22, "road": "NH-715"},
    {"id": "DEL-8808", "vehicle": "TRK-905", "origin": "Agartala", "destination": "Udaipur", "commodity": "FOOD", "status": "ON_TRACK", "eta_minutes": 42, "risk": 12, "road": "NH-108"},
]

DEMO_FIELD_REPORTS = [
    {"id": "FR-1002", "officer_email": "field@neris.demo", "officer_name": "R. Marak", "type": "ROAD_DAMAGE", "description": "Asphalt scouring near culvert, single lane passable", "road_id": "rd-sh9", "location": "SH-9, Barak valley", "lat": 24.55, "lng": 92.77, "severity": "WARNING", "status": "VERIFIED", "created_minutes_ago": 95},
    {"id": "FR-1001", "officer_email": "field@neris.demo", "officer_name": "R. Marak", "type": "LANDSLIDE", "description": "Fresh debris slide onto shoulder, work crew on site", "road_id": "rd-nh6", "location": "NH-6, near Sonapur", "lat": 26.07, "lng": 91.63, "severity": "HIGH", "status": "SUBMITTED", "created_minutes_ago": 40},
]

DEMO_ENVIRONMENT = [
    {"id": "rain-shillong", "kind": "RAIN", "name": "Meghalaya Hills rain cell", "lat": 25.60, "lng": 91.62, "base_intensity_mm_h": 28, "base_radius_km": 40},
    {"id": "rain-tezpur", "kind": "RAIN", "name": "Tezpur valley rain", "lat": 26.63, "lng": 92.80, "base_intensity_mm_h": 14, "base_radius_km": 30},
    {"id": "rain-barak", "kind": "RAIN", "name": "Barak valley monsoon band", "lat": 24.60, "lng": 92.75, "base_intensity_mm_h": 22, "base_radius_km": 35},
    {"id": "ls-sonapur", "kind": "LANDSLIDE", "name": "Sonapur slope", "lat": 26.07, "lng": 91.63, "slide_type": "DEBRIS_FLOW", "probability": 0.78},
    {"id": "ls-kohima", "kind": "LANDSLIDE", "name": "Kohima bypass cut slope", "lat": 25.78, "lng": 93.90, "slide_type": "ROCKFALL", "probability": 0.66},
    {"id": "ls-aizawl", "kind": "LANDSLIDE", "name": "Aizawl–Silchar road cut", "lat": 24.00, "lng": 92.80, "slide_type": "SHALLOW_SLIDE", "probability": 0.58},
]


def _current_environment(events):
    """Simulated live weather: intensity oscillates over time so the map visibly updates (DEMO)."""
    import math
    now = datetime.now(timezone.utc)
    t = now.hour * 60 + now.minute + now.second / 60.0
    rain = []
    landslides = []
    for e in events:
        if e["kind"] == "RAIN":
            phase = (sum(ord(c) for c in e["id"]) % 100) / 100.0 * 6.283
            factor = 1 + 0.35 * math.sin(t * 0.35 + phase)
            intensity = round(e["base_intensity_mm_h"] * factor, 1)
            radius = round(e["base_radius_km"] * (0.7 + 0.3 * factor), 1)
            rain.append({
                "id": e["id"], "kind": "RAIN", "name": e["name"], "lat": e["lat"], "lng": e["lng"],
                "intensity_mm_h": intensity, "radius_km": radius,
                "level": "HEAVY" if intensity >= 20 else "MODERATE",
            })
        elif e["kind"] == "LANDSLIDE":
            landslides.append({
                "id": e["id"], "kind": "LANDSLIDE", "name": e["name"], "lat": e["lat"], "lng": e["lng"],
                "slide_type": e["slide_type"], "probability": e["probability"],
            })
    return {"rain": rain, "landslides": landslides}


DEMO_SUPPLY = [
    {"commodity": "MEDICINE", "at_risk_count": 7, "severity": "CRITICAL"},
    {"commodity": "FOOD", "at_risk_count": 13, "severity": "HIGH"},
    {"commodity": "WATER", "at_risk_count": 8, "severity": "WARNING"},
    {"commodity": "FUEL", "at_risk_count": 3, "severity": "INFO"},
]

SEED_VERSION = 5


async def seed_dashboard():
    meta = await db.meta.find_one({"key": "seed_version"})
    current = meta["value"] if meta else 0
    if current >= SEED_VERSION:
        return
    for coll in ["roads", "incidents", "vehicles", "villages", "supply_risks", "deliveries", "field_reports", "environment_events"]:
        await db[coll].delete_many({})
    await db.roads.insert_many([{**r, "source": "DEMO"} for r in DEMO_ROADS])
    await db.incidents.insert_many([{**i, "source_tag": "DEMO"} for i in DEMO_INCIDENTS])
    await db.vehicles.insert_many([{**v, "source": "DEMO"} for v in DEMO_VEHICLES])
    await db.villages.insert_many([{**v, "source": "DEMO"} for v in DEMO_VILLAGES])
    await db.supply_risks.insert_many([{**s, "source": "DEMO"} for s in DEMO_SUPPLY])
    await db.deliveries.insert_many([{**d, "source": "DEMO"} for d in DEMO_DELIVERIES])
    await db.field_reports.insert_many([{**f, "source": "DEMO"} for f in DEMO_FIELD_REPORTS])
    await db.environment_events.insert_many([{**e, "source": "DEMO"} for e in DEMO_ENVIRONMENT])
    await db.meta.update_one({"key": "seed_version"}, {"$set": {"value": SEED_VERSION}}, upsert=True)


# =============================
# Supply-chain seed (depots, NER villages, routes, gov vehicles)
# =============================

SUPPLY_DEPOTS = [
    {"id": "dep-shillong", "name": "Shillong Central Depot", "lat": 25.5759, "lon": 91.8827, "state": "Meghalaya",
     "inventory": {"food": 8000, "water": 12000, "medicine": 2500, "fuel": 4000}},
    {"id": "dep-guwahati", "name": "Guwahati Regional Depot", "lat": 26.1445, "lon": 91.7362, "state": "Assam",
     "inventory": {"food": 15000, "water": 18000, "medicine": 5000, "fuel": 7000}},
    {"id": "dep-imphal", "name": "Imphal Depot", "lat": 24.8170, "lon": 93.9368, "state": "Manipur",
     "inventory": {"food": 6000, "water": 9000, "medicine": 1800, "fuel": 3000}},
    {"id": "dep-agartala", "name": "Agartala Depot", "lat": 23.8315, "lon": 91.2866, "state": "Tripura",
     "inventory": {"food": 5500, "water": 8000, "medicine": 1600, "fuel": 2500}},
    {"id": "dep-aizawl", "name": "Aizawl Depot", "lat": 23.7271, "lon": 92.7176, "state": "Mizoram",
     "inventory": {"food": 4000, "water": 6500, "medicine": 1200, "fuel": 2000}},
]

SUPPLY_VILLAGES = [
    {"id": "vil-nongstoin", "name": "Nongstoin", "lat": 25.5060, "lon": 91.0085, "state": "Meghalaya", "depot_id": "dep-shillong",
     "population": 28700, "demand": {"food": 420, "water": 610, "medicine": 90, "fuel": 70}},
    {"id": "vil-jowai", "name": "Jowai", "lat": 25.4500, "lon": 92.2500, "state": "Meghalaya", "depot_id": "dep-shillong",
     "population": 28400, "demand": {"food": 380, "water": 540, "medicine": 80, "fuel": 60}},
    {"id": "vil-williamnagar", "name": "Williamnagar", "lat": 25.5700, "lon": 90.6000, "state": "Meghalaya", "depot_id": "dep-guwahati",
     "population": 18200, "demand": {"food": 310, "water": 480, "medicine": 70, "fuel": 55}},
    {"id": "vil-ukhrul", "name": "Ukhrul", "lat": 24.8200, "lon": 94.3600, "state": "Manipur", "depot_id": "dep-imphal",
     "population": 24700, "demand": {"food": 360, "water": 520, "medicine": 95, "fuel": 65}},
    {"id": "vil-senapati", "name": "Senapati", "lat": 25.3000, "lon": 94.1500, "state": "Manipur", "depot_id": "dep-imphal",
     "population": 19100, "demand": {"food": 290, "water": 430, "medicine": 75, "fuel": 50}},
    {"id": "vil-kohima-hq", "name": "Kohima", "lat": 25.6750, "lon": 94.1086, "state": "Nagaland", "depot_id": "dep-guwahati",
     "population": 99000, "demand": {"food": 900, "water": 1300, "medicine": 220, "fuel": 180}},
    {"id": "vil-mokokchung-hq", "name": "Mokokchung", "lat": 26.3300, "lon": 94.5200, "state": "Nagaland", "depot_id": "dep-guwahati",
     "population": 35900, "demand": {"food": 410, "water": 590, "medicine": 85, "fuel": 70}},
    {"id": "vil-tuensang", "name": "Tuensang", "lat": 26.2700, "lon": 94.8300, "state": "Nagaland", "depot_id": "dep-guwahati",
     "population": 36700, "demand": {"food": 400, "water": 580, "medicine": 88, "fuel": 72}},
]


def _haversine_km(lat1, lon1, lat2, lon2):
    import math
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


def _snap_edge(roads, lat, lon):
    """Return (edge_id, node_u, node_v, geometry) for the nearest road, or None."""
    import pandas as pd
    from shapely.geometry import Point
    import geopandas as gpd
    if roads is None or len(roads) == 0:
        return None
    try:
        roads_m = roads.to_crs(32646)
        pt = gpd.GeoDataFrame([{"geometry": Point(lon, lat)}], crs="EPSG:4326").to_crs(32646)
        keep = [c for c in ["edge_id", "geometry", "u", "v"] if c in roads_m.columns]
        nearest = gpd.sjoin_nearest(pt, roads_m[keep], how="left", max_distance=25000, distance_col="dist_m")
        if nearest.empty or pd.isna(nearest.iloc[0].get("edge_id")):
            return None
        eid = str(nearest.iloc[0]["edge_id"])
        orig = roads[roads["edge_id"].astype(str) == eid]
        if orig.empty:
            return None
        row = orig.iloc[0]
        geom = row.geometry
        u = str(row["u"]) if "u" in orig.columns and pd.notna(row.get("u")) else None
        v = str(row["v"]) if "v" in orig.columns and pd.notna(row.get("v")) else None
        if (u is None or v is None) and geom is not None and not geom.is_empty:
            coords = list(geom.coords)
            u = u or f"{coords[0][0]:.5f},{coords[0][1]:.5f}"
            v = v or f"{coords[-1][0]:.5f},{coords[-1][1]:.5f}"
        return {"edge_id": eid, "u": u, "v": v, "geometry": geom}
    except Exception:
        return None


def _build_seed_graph(roads):
    import networkx as nx
    import pandas as pd
    G = nx.Graph()
    if roads is None or len(roads) == 0:
        return G
    has_uv = "u" in roads.columns and "v" in roads.columns
    for _, r in roads.iterrows():
        geom = r.geometry
        if geom is None or geom.is_empty:
            continue
        if has_uv and pd.notna(r.get("u")) and pd.notna(r.get("v")):
            u, v = str(r["u"]), str(r["v"])
        else:
            coords = list(geom.coords)
            u = f"{coords[0][0]:.5f},{coords[0][1]:.5f}"
            v = f"{coords[-1][0]:.5f},{coords[-1][1]:.5f}"
        length = r.get("length")
        if length is None or (isinstance(length, float) and pd.isna(length)):
            length = float(r.get("length_km") or 0) * 1000.0 or (geom.length if geom else 1.0)
        G.add_edge(u, v, edge_id=str(r["edge_id"]), length=float(length), geometry=geom)
    return G


def _path_edge_ids(G, src, tgt):
    import networkx as nx
    if not src or not tgt or src not in G or tgt not in G:
        return [], src, tgt, 0.0
    try:
        nodes = nx.shortest_path(G, src, tgt, weight="length")
    except Exception:
        return [], src, tgt, 0.0
    eids = []
    total = 0.0
    for a, b in zip(nodes[:-1], nodes[1:]):
        data = G[a][b]
        eids.append(data.get("edge_id"))
        total += float(data.get("length") or 0)
    return eids, src, tgt, total


def _interpolate_line(depot, village, n=20):
    coords = []
    for i in range(n):
        t = i / (n - 1) if n > 1 else 0
        lat = depot["lat"] + (village["lat"] - depot["lat"]) * t
        lon = depot["lon"] + (village["lon"] - depot["lon"]) * t
        coords.append((lat, lon))
    return coords


async def seed_supply_chain():
    """Idempotent NER supply-chain demo: depots, villages, routes, gov vehicles, GPS traces."""
    import os
    from pathlib import Path

    depots_exist = await db.depots.count_documents({"id": "dep-shillong"})
    if not depots_exist:
        now = datetime.now(timezone.utc).isoformat()
        await db.depots.insert_many([{**d, "source": "SUPPLY_CHAIN", "created_at": now} for d in SUPPLY_DEPOTS])

    for vil in SUPPLY_VILLAGES:
        if await db.villages.count_documents({"id": vil["id"]}) == 0:
            await db.villages.insert_one({
                **vil,
                "district": vil["name"],
                "isolation_risk": "MEDIUM",
                "days_to_stockout": 6,
                "primary_commodity": "FOOD",
                "source": "SUPPLY_CHAIN",
            })

    roads = None
    try:
        import geopandas as gpd
        data_dir = Path(__file__).resolve().parent / "data" / "processed"
        roads_path = os.environ.get("ROADS_PARQUET", str(data_dir / "roads.parquet"))
        if Path(roads_path).exists():
            roads = gpd.read_parquet(roads_path)
            if "bridge_id" not in roads.columns:
                import hashlib
                def _get_bridge_id(eid):
                    h = int(hashlib.md5(str(eid).encode()).hexdigest(), 16)
                    return f"br_{eid}" if h % 20 == 0 else None
                roads["bridge_id"] = roads["edge_id"].apply(_get_bridge_id)
                roads.to_parquet(roads_path)
    except Exception:
        roads = None

    G = _build_seed_graph(roads) if roads is not None else None
    depot_by_id = {d["id"]: d for d in SUPPLY_DEPOTS}

    routes = []
    for vil in SUPPLY_VILLAGES:
        depot = depot_by_id[vil["depot_id"]]
        path = []
        depot_node = village_node = None
        length_m = _haversine_km(depot["lat"], depot["lon"], vil["lat"], vil["lon"]) * 1000.0
        if G is not None and G.number_of_edges() > 0:
            d_edge = _snap_edge(roads, depot["lat"], depot["lon"])
            v_edge = _snap_edge(roads, vil["lat"], vil["lon"])
            if d_edge and v_edge:
                path, depot_node, village_node, length_m = _path_edge_ids(
                    G, d_edge.get("u"), v_edge.get("u"),
                )
                if not path:
                    path, depot_node, village_node, length_m = _path_edge_ids(
                        G, d_edge.get("v"), v_edge.get("v"),
                    )
                if not path:
                    path = [d_edge["edge_id"], v_edge["edge_id"]]
                    depot_node, village_node = d_edge.get("u"), v_edge.get("u")
                    length_m = _haversine_km(depot["lat"], depot["lon"], vil["lat"], vil["lon"]) * 1000.0
        eta = max(15, int((length_m / 1000.0) / 40.0 * 60))
        routes.append({
            "route_id": f"sr-{vil['id']}",
            "village_id": vil["id"],
            "depot_id": vil["depot_id"],
            "path": path,
            "depot_node": depot_node,
            "village_node": village_node,
            "eta_minutes": eta,
            "active": True,
            "origin": {"lat": depot["lat"], "lon": depot["lon"], "name": depot["name"]},
            "destination": {"lat": vil["lat"], "lon": vil["lon"], "name": vil["name"]},
            "source": "SUPPLY_CHAIN",
        })

    if await db.supply_routes.count_documents({"route_id": "sr-vil-nongstoin"}) == 0:
        await db.supply_routes.insert_many(routes)

    drivers = [
        {"name": "R. Lyngdoh", "phone": "+91-94361-11001", "license": "ML-042011-0012345"},
        {"name": "P. Sharma", "phone": "+91-98640-22002", "license": "AS-031998-0098765"},
        {"name": "T. Singh", "phone": "+91-84140-33003", "license": "MN-2015-4455667"},
        {"name": "N. Ao", "phone": "+91-94360-44004", "license": "NL-2008-1122334"},
        {"name": "S. Debbarma", "phone": "+91-98625-55005", "license": "TR-2012-7788990"},
        {"name": "L. Chhangte", "phone": "+91-94361-66006", "license": "MZ-2016-3344556"},
        {"name": "B. Kalita", "phone": "+91-99540-77007", "license": "AS-2005-5566778"},
        {"name": "K. Angami", "phone": "+91-89740-88008", "license": "NL-2011-9900112"},
    ]
    gov_vehicles = [
        {"government_id": "AS-01-AB-1234", "vehicle_type": "truck", "status": "active", "department": "Assam SDMA"},
        {"government_id": "ML-02-CD-2345", "vehicle_type": "truck", "status": "active", "department": "Meghalaya SDMA"},
        {"government_id": "MN-03-EF-3456", "vehicle_type": "truck", "status": "active", "department": "Manipur SDMA"},
        {"government_id": "NL-04-GH-4567", "vehicle_type": "ambulance", "status": "idle", "department": "Nagaland Health"},
        {"government_id": "TR-05-IJ-5678", "vehicle_type": "supply_truck", "status": "idle", "department": "Tripura Logistics"},
        {"government_id": "MZ-06-KL-6789", "vehicle_type": "supply_truck", "status": "idle", "department": "Mizoram SDMA"},
        {"government_id": "AS-07-MN-7890", "vehicle_type": "rescue_vehicle", "status": "maintenance", "department": "Assam SDRF"},
        {"government_id": "NL-08-OP-8901", "vehicle_type": "rescue_vehicle", "status": "maintenance", "department": "Nagaland SDRF"},
    ]

    now = datetime.now(timezone.utc)
    tracking_batch = []
    for i, spec in enumerate(gov_vehicles):
        if await db.vehicles.count_documents({"government_id": spec["government_id"]}) > 0:
            continue
        vil = SUPPLY_VILLAGES[i]
        depot = depot_by_id[vil["depot_id"]]
        route = routes[i]
        is_active = spec["status"] == "active"
        loc_lat, loc_lon = depot["lat"], depot["lon"]
        if is_active:
            loc_lat = depot["lat"] + (vil["lat"] - depot["lat"]) * 0.35
            loc_lon = depot["lon"] + (vil["lon"] - depot["lon"]) * 0.35
        vid = str(uuid.uuid4())
        cargo = {"food": 120, "water": 180, "medicine": 40, "fuel": 25} if is_active else None
        assigned = None
        if is_active:
            assigned = {
                "route_id": route["route_id"],
                "path": route["path"],
                "destination": vil["name"],
                "village_id": vil["id"],
                "depot_id": depot["id"],
            }
        vehicle = {
            "id": vid,
            "government_id": spec["government_id"],
            "number": spec["government_id"],
            "vehicle_type": spec["vehicle_type"],
            "type": spec["vehicle_type"].upper(),
            "department": spec["department"],
            "lat": loc_lat,
            "lng": loc_lon,
            "lon": loc_lon,
            "location": {"lat": loc_lat, "lon": loc_lon},
            "heading": 90,
            "speed": 32 if is_active else 0,
            "status": spec["status"],
            "destination": vil["name"] if is_active else "—",
            "eta_minutes": route["eta_minutes"] if is_active else None,
            "cargo": cargo,
            "commodity": "FOOD" if cargo else None,
            "assigned_route": assigned,
            "driver": drivers[i],
            "source": "SUPPLY_CHAIN",
            "created_at": now.isoformat(),
        }
        await db.vehicles.insert_one(vehicle)

        if is_active:
            pts = _interpolate_line(depot, vil, 20)
            for j, (plat, plon) in enumerate(pts):
                ts = (now - timedelta(minutes=(19 - j) * 8)).isoformat()
                tracking_batch.append({
                    "id": str(uuid.uuid4()),
                    "vehicle_id": vid,
                    "government_id": spec["government_id"],
                    "lat": plat,
                    "lon": plon,
                    "speed": 28 + (j % 5),
                    "heading": 90,
                    "timestamp": ts,
                    "source": "SUPPLY_CHAIN",
                })

    if tracking_batch:
        existing = await db.vehicle_tracking.count_documents({"source": "SUPPLY_CHAIN"})
        if existing == 0:
            await db.vehicle_tracking.insert_many(tracking_batch)
