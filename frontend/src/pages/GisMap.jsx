import { useCallback, useEffect, useState } from "react";
import { Layers } from "lucide-react";
import api from "@/lib/api";
import { ensureWS, subscribeWS } from "@/lib/ws";
import { useAuth } from "@/context/AuthContext";
import NavRail from "@/components/NavRail";
import PageHeader from "@/components/PageHeader";
import NerMap, { STATUS_COLORS } from "@/components/NerMap";
import RoadControlDrawer from "@/components/RoadControlDrawer";
import HazardInjectionPanel from "@/components/HazardInjectionPanel";
import PipelineStatusWidget from "@/components/PipelineStatusWidget";
import PrePositioningPanel from "@/components/PrePositioningPanel";
import { useToast } from "@/hooks/use-toast";

// Pipeline API helper — fetches with JWT auth
const API_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";

const authFetch = async (path) => {
  const token = localStorage.getItem("token");
  if (!token) return null;
  try {
    const res = await fetch(`${API_URL}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return null;
    return res.json();
  } catch { return null; }
};

export default function GisMap() {
  const { user } = useAuth();
  const { toast } = useToast();
  const canSeeLiveVehicles = user && ["SUPER_ADMIN", "GOVERNMENT_ADMIN", "GOVERNMENT_OFFICER", "DISTRICT_OFFICER", "FIELD_OFFICER"].includes(user.role);

  // Existing state (teammate's code)
  const [data, setData] = useState(null);
  const [zones, setZones] = useState([]);
  const [environment, setEnvironment] = useState(null);
  const [layers, setLayers] = useState({ roads: true, vehicles: true, incidents: true, traffic: false, hazards: true, altRoutes: true });
  const [selectedRoad, setSelectedRoad] = useState(null);
  const [isDroppingPin, setIsDroppingPin] = useState(false);
  const [pinCoords, setPinCoords] = useState(null);

  // NEW: Pipeline state
  const [depots, setDepots] = useState([]);
  const [villages, setVillages] = useState([]);
  const [pipelineVehicles, setPipelineVehicles] = useState([]);
  const [hazards, setHazards] = useState([]);
  const [blockedEdges, setBlockedEdges] = useState([]);
  const [alternativeRoutes, setAlternativeRoutes] = useState([]);
  const [prePositioningRoutes, setPrePositioningRoutes] = useState([]);

  // Existing: fetch dashboard data
  const fetchAll = useCallback(async () => {
    try {
      const [{ data: d }, { data: z }, { data: env }] = await Promise.all([
        api.get("/dashboard/summary"),
        api.get("/emergency-zones"),
        api.get("/environment"),
      ]);
      console.log("GisMap data loaded:", d ? "YES" : "NO");
      setData(d);
      setZones(z);
      setEnvironment(env);
    } catch (e) {
      console.error("GisMap fetchAll error:", e);
    }
  }, []);

  // NEW: fetch pipeline data
  const fetchPipelineData = useCallback(async () => {
    const [depotsData, villagesData, vehiclesData] = await Promise.all([
      authFetch("/api/pipeline/depots"),
      authFetch("/api/pipeline/villages"),
      canSeeLiveVehicles ? authFetch("/api/vehicles/active") : Promise.resolve(null),
    ]);
    if (depotsData?.depots) setDepots(depotsData.depots);
    if (villagesData?.villages) setVillages(villagesData.villages);
    if (vehiclesData?.vehicles) setPipelineVehicles(vehiclesData.vehicles);
  }, [canSeeLiveVehicles]);

  useEffect(() => {
    fetchAll();
    fetchPipelineData();
    const t1 = setInterval(fetchAll, 15000);
    const t2 = setInterval(fetchPipelineData, 30000);
    return () => { clearInterval(t1); clearInterval(t2); };
  }, [fetchAll, fetchPipelineData]);

  // WebSocket — handle BOTH old and new events
  useEffect(() => {
    ensureWS();
    const unsub = subscribeWS((msg) => {
      const eventType = msg.type || msg.event;

      if (eventType === "hazard_injected") {
        const hazard = msg.hazard || {
          lat: msg.lat, lon: msg.lon,
          hazard_type: msg.hazard_type,
          source: msg.source, severity: msg.severity,
          edge_id: msg.matched_edge_id,
          matched_road_geometry: msg.matched_road_geometry,
          hazard_radius_m: msg.hazard_radius_m || 500,
        };
        setHazards(prev => [...prev, hazard]);
        if (msg.matched_road_geometry) {
          setBlockedEdges(prev => [...prev, {
            edge_id: msg.matched_edge_id,
            geometry: msg.matched_road_geometry,
            matched_road_geometry: msg.matched_road_geometry,
          }]);
        }
        if (msg.alternative_routes) {
          setAlternativeRoutes(prev => [...prev, ...msg.alternative_routes]);
        }
        toast({ title: "⚠ Hazard Injected", description: `${hazard.hazard_type || 'Unknown'} hazard reported` });
        fetchAll();
      }
      else if (eventType === "vehicle_location_update") {
        setPipelineVehicles(prev => prev.map(v =>
          v.government_id === msg.government_id
            ? { ...v, lat: msg.location?.lat ?? msg.lat ?? v.lat, lon: msg.location?.lon ?? msg.lon ?? v.lon, speed: msg.speed_kmh ?? msg.speed ?? v.speed }
            : v
        ));
      }
      else if (eventType === "ai_prediction") {
        setHazards(prev => [...prev, {
          lat: msg.lat, lon: msg.lon,
          hazard_type: msg.dominant_hazard,
          source: "ai_prediction",
          severity: msg.risk_level,
          hazard_radius_m: 500,
        }]);
        if (msg.pre_positioning_plan?.routes) {
          setPrePositioningRoutes(prev => [...prev, ...msg.pre_positioning_plan.routes]);
        }
        toast({ title: "🤖 AI Prediction", description: `Risk: ${msg.risk_level?.toUpperCase()}` });
      }
      else if (eventType === "vehicle_rerouted") {
        toast({ title: "Vehicle Rerouted", description: `${msg.government_id} rerouted` });
        fetchPipelineData();
      }
      else if (["ROAD_STATUS_CHANGED", "INCIDENT_CREATED", "INCIDENT_VERIFIED", "EMERGENCY_DECLARED", "EMERGENCY_ENDED", "VEHICLE_ADDED"].includes(eventType)) {
        fetchAll();
      }
    });
    return unsub;
  }, [fetchAll, fetchPipelineData, toast]);

  // Combine vehicles from dashboard + pipeline
  const allVehicles = canSeeLiveVehicles
    ? [...(data?.vehicles || []), ...pipelineVehicles]
    : pipelineVehicles;

  return (
    <div className="h-screen flex bg-[var(--surface-base)] overflow-hidden" data-testid="gis-map-page">
      <NavRail />
      <div className="flex-1 flex flex-col min-w-0">
        <PageHeader title="GIS MAP" chip="LIVE ROAD STATE" />
        <div className="flex-1 relative min-h-0">
          {/* ALWAYS render NerMap — no data conditional */}
          <NerMap
            roads={data?.roads}
            vehicles={allVehicles}
            incidents={data?.incidents?.filter((i) => i.status !== "RESOLVED") || []}
            hazards={hazards}
            blockedEdges={blockedEdges}
            alternativeRoutes={alternativeRoutes}
            prePositioningRoutes={prePositioningRoutes}
            depots={depots}
            villages={villages}
            layers={{ ...layers, vehicles: layers.vehicles && canSeeLiveVehicles }}
            onRoadClick={(props) => !isDroppingPin && setSelectedRoad(props)}
            zones={zones}
            environment={environment}
            isDroppingPin={isDroppingPin}
            onMapClick={(coords) => {
              if (isDroppingPin) {
                setPinCoords(coords);
                setIsDroppingPin(false);
              }
            }}
          />

          {/* Left: Hazard Injection + Pre-positioning Panel */}
          <div className="absolute top-3 left-3 z-10 pointer-events-auto flex flex-col gap-2 w-80 max-h-[calc(100%-100px)] overflow-y-auto">
            <HazardInjectionPanel
              isDroppingPin={isDroppingPin}
              setIsDroppingPin={setIsDroppingPin}
              pinCoords={pinCoords}
            />
            <PrePositioningPanel />
          </div>

          {/* Top-right: Pipeline Status */}
          <div className="absolute top-3 right-56 z-10 pointer-events-none">
            <PipelineStatusWidget />
          </div>

          {/* Layer toggles */}
          <div className="absolute top-3 right-3 bg-white border hairline rounded-md shadow-sm p-2.5 w-44 z-10" data-testid="gis-layer-control">
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-neutral-500 font-semibold mb-2">
              <Layers size={12} /> Layers
            </div>
            {[
              { key: "roads", label: "Road Status" },
              ...(canSeeLiveVehicles ? [{ key: "vehicles", label: "Vehicles (live)" }] : []),
              { key: "incidents", label: "Incidents" },
              { key: "hazards", label: "Hazards" },
              { key: "altRoutes", label: "Alt Routes" },
              { key: "traffic", label: "Traffic" },
            ].map((l) => (
              <label key={l.key} className="flex items-center gap-2 py-1 text-[12px] text-neutral-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={layers[l.key] ?? true}
                  onChange={(e) => setLayers((s) => ({ ...s, [l.key]: e.target.checked }))}
                  className="w-3.5 h-3.5 accent-[var(--accent-primary)]"
                  data-testid={`gis-layer-toggle-${l.key}`}
                />
                {l.label}
              </label>
            ))}
          </div>

          {/* Legend */}
          <div className="absolute bottom-3 left-3 bg-white/95 border hairline rounded-md shadow-sm px-3 py-2 z-10 pointer-events-auto" data-testid="gis-map-legend">
            <div className="grid grid-cols-2 gap-x-4 gap-y-1">
              {[
                ["OPEN", "Open"], ["AT_RISK", "At Risk"], ["RESTRICTED", "Restricted"],
                ["BLOCKED", "Blocked"], ["GOVERNMENT_CLOSED", "Gov Closed"], ["UNKNOWN", "Unknown"],
              ].map(([k, label]) => (
                <div key={k} className="flex items-center gap-1.5 text-[10.5px] text-neutral-600">
                  <span className="w-4 h-[3px] rounded-full" style={{ background: STATUS_COLORS[k] }} />
                  {label}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {selectedRoad && data?.roads?.features && (
        <RoadControlDrawer
          road={data.roads.features.find((f) => f.properties.id === selectedRoad.id)?.properties || selectedRoad}
          onClose={() => setSelectedRoad(null)}
          onChanged={(updated) => { setSelectedRoad(updated); fetchAll(); }}
        />
      )}
    </div>
  );
}