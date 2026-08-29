import api from "./api";

// 1. POST /api/admin/manual-hazard
export const injectHazard = async (lat, lon, hazardType, severity, notes) => {
  const { data } = await api.post("/admin/manual-hazard", {
    lat,
    lon,
    hazard_type: hazardType,
    severity,
    notes,
  });
  return data;
};

// 2. POST /api/admin/close-road
export const closeRoad = async (edgeId, closed) => {
  const { data } = await api.post("/admin/close-road", {
    edge_id: edgeId,
    closed,
  });
  return data;
};

// 3. GET /api/pipeline/status
export const getPipelineStatus = async () => {
  const { data } = await api.get("/pipeline/status");
  return data;
};

// 4. GET /api/pipeline/roads?limit=10
export const getRoadNetwork = async (limit = 10) => {
  const { data } = await api.get(`/pipeline/roads?limit=${limit}`);
  return data;
};

// 5. GET /api/pipeline/hazards?limit=10
export const getHazards = async (limit = 10) => {
  const { data } = await api.get(`/pipeline/hazards?limit=${limit}`);
  return data;
};

// 6. POST /api/pipeline/route
export const calculateRoute = async (originLat, originLon, destLat, destLon, minSurvivability = 0.85, kPaths = 3) => {
  const { data } = await api.post("/pipeline/route", {
    origin_lat: originLat,
    origin_lon: originLon,
    dest_lat: destLat,
    dest_lon: destLon,
    min_survivability: minSurvivability,
    k_paths: kPaths,
  });
  return data;
};

// 7. POST /api/pipeline/logistics/optimize
export const optimizeLogistics = async (depots, villages, inventory, demand, commodities) => {
  const { data } = await api.post("/pipeline/logistics/optimize", {
    depots,
    villages,
    inventory,
    demand,
    commodities,
  });
  return data;
};

// 8. POST /api/pipeline/orchestrate
export const orchestratePipeline = async (depots, villages, inventory, demand, commodities) => {
  const { data } = await api.post("/pipeline/orchestrate", {
    depots,
    villages,
    inventory,
    demand,
    commodities,
  });
  return data;
};

// 9. POST /api/pipeline/replan
export const replanRoutes = async (edgeId, blockagePct = 0.95, hazardType = "landslide") => {
  const { data } = await api.post("/pipeline/replan", {
    edge_id: edgeId,
    blockage_pct: blockagePct,
    hazard_type: hazardType,
  });
  return data;
};
