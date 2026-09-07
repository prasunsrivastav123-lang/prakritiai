import api from "./api";

// 1. POST /api/admin/manual-hazard (legacy)
export const injectHazard = async (lat, lon, hazardType, severity, notes) => {
  const { data } = await api.post("/admin/manual-hazard", {
    lat, lon, hazard_type: hazardType, severity, notes,
  });
  return data;
};

// 1b. POST /api/pipeline/inject-and-optimize
export const injectAndOptimize = async (lat, lon, hazardType, severity, notes = "", source = "government") => {
  console.log("injectAndOptimize called:", { lat, lon, hazardType, severity, notes, source });
  try {
    const { data } = await api.post("/pipeline/inject-and-optimize", {
      lat: parseFloat(lat),
      lon: parseFloat(lon),
      hazard_type: hazardType,
      severity,
      notes,
      source: source ? source.toLowerCase() : "government",
    });
    console.log("injectAndOptimize result:", data);
    return data;
  } catch (err) {
    console.error("injectAndOptimize ERROR:", err.response?.data || err.message);
    throw err;
  }
};

// 1c. POST /api/pipeline/ai-predict — FIXED: now takes (lat, lon, params)
export const getAIPrediction = async (lat, lon, params = {}) => {
  console.log("getAIPrediction called:", { lat, lon, params });
  const defaults = {
    rainfall_24h: 150,
    rainfall_7d: 400,
    soil_moisture: 0.85,
    slope: 35,
    elevation: 1400,
    proximity_to_river: 300,
    historical_landslide_frequency: 7,
    historical_flood_frequency: 5,
    ...params,
  };
  try {
    const { data } = await api.post("/pipeline/ai-predict", {
      lat: parseFloat(lat),
      lon: parseFloat(lon),
      ...defaults,
    });
    console.log("getAIPrediction result:", data);
    return data;
  } catch (err) {
    console.error("getAIPrediction ERROR:", err.response?.data || err.message);
    throw err;
  }
};

// 2. POST /api/admin/close-road
export const closeRoad = async (edgeId, closed) => {
  const { data } = await api.post("/admin/close-road", {
    edge_id: edgeId, closed,
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

// 5b. GET /api/pipeline/depots, /villages, /supply-routes
export const getDepots = async () => {
  const { data } = await api.get("/pipeline/depots");
  return data;
};

export const getVillages = async () => {
  const { data } = await api.get("/pipeline/villages");
  return data;
};

export const getSupplyRoutes = async () => {
  const { data } = await api.get("/pipeline/supply-routes");
  return data;
};

// 5c. Traffic
export const getTraffic = async (lat, lon) => {
  const { data } = await api.get(`/pipeline/traffic?lat=${lat}&lon=${lon}`);
  return data;
};

export const getTrafficRoute = async (originLat, originLon, destLat, destLon) => {
  const { data } = await api.post("/pipeline/traffic-route", {
    origin_lat: originLat, origin_lon: originLon,
    dest_lat: destLat, dest_lon: destLon,
  });
  return data;
};

// 6. POST /api/pipeline/route
export const calculateRoute = async (originLat, originLon, destLat, destLon, minSurvivability = 0.85, kPaths = 3) => {
  const { data } = await api.post("/pipeline/route", {
    origin_lat: originLat, origin_lon: originLon,
    dest_lat: destLat, dest_lon: destLon,
    min_survivability: minSurvivability, k_paths: kPaths,
  });
  return data;
};

// 7. POST /api/pipeline/logistics/optimize
export const optimizeLogistics = async (depots, villages, inventory, demand, commodities) => {
  const { data } = await api.post("/pipeline/logistics/optimize", {
    depots, villages, inventory, demand, commodities,
  });
  return data;
};

// 8. POST /api/pipeline/orchestrate
export const orchestratePipeline = async (depots, villages, inventory, demand, commodities) => {
  const { data } = await api.post("/pipeline/orchestrate", {
    depots, villages, inventory, demand, commodities,
  });
  return data;
};

// 9. POST /api/pipeline/replan
export const replanRoutes = async (edgeId, blockagePct = 0.95, hazardType = "landslide") => {
  const { data } = await api.post("/pipeline/replan", {
    edge_id: edgeId, blockage_pct: blockagePct, hazard_type: hazardType,
  });
  return data;
};

// 10. Vehicles Management & Tracking
export const getActiveVehicles = async () => {
  const { data } = await api.get("/vehicles/active");
  return data;
};

export const trackVehicles = async (status) => {
  const url = status ? `/vehicles/track?status=${status}` : "/vehicles/track";
  const { data } = await api.get(url);
  return data;
};

export const trackByGovId = async (govId) => {
  const { data } = await api.get(`/vehicles/track/${govId}`);
  return data;
};

export const updateVehicleLocation = async (govId, lat, lon, speed, heading, status) => {
  const { data } = await api.post(`/vehicles/track/${govId}/update`, {
    lat, lon, speed_kmh: speed, heading, status,
  });
  return data;
};

export const registerVehicle = async (vehicleData) => {
  const { data } = await api.post("/vehicles/register", vehicleData);
  return data;
};

export const dispatchVehicle = async (id, routeData) => {
  const { data } = await api.post(`/vehicles/${id}/dispatch`, routeData);
  return data;
};

export const recallVehicle = async (id) => {
  const { data } = await api.post(`/vehicles/${id}/recall`);
  return data;
};

export const searchByGovId = async (govId) => {
  const { data } = await api.get(`/vehicles/search?government_id=${govId}`);
  return data;
};

export const getTrackingHistory = async (id, limit = 50) => {
  const { data } = await api.get(`/vehicles/${id}/tracking-history?limit=${limit}`);
  return data;
};

export const assignCargo = async (id, cargo) => {
  const { data } = await api.post(`/vehicles/${id}/assign-cargo`, { cargo });
  return data;
};