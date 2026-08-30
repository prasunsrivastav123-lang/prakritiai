import { useEffect, useRef } from "react";
import { Map as MLMap, NavigationControl, Marker, Popup } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

export const STATUS_COLORS = {
  OPEN: "#1E8E3E",
  AT_RISK: "#C77C00",
  RESTRICTED: "#D9622B",
  BLOCKED: "#DC2626",
  GOVERNMENT_CLOSED: "#8A1512",
  UNKNOWN: "#8A9099",
  LOCAL: "#64748B",
  ALT_ROUTE: "#16A34A",
  PRE_POS: "#9333EA",
};

export const HAZARD_COLORS = {
  FLOOD_GOV: "#2563EB",
  FLOOD_AI: "#06B6D4",
  LANDSLIDE_GOV: "#EA580C",
  LANDSLIDE_AI: "#EAB308",
};

// Safe coordinate helper — prevents NaN crashes
const getCoords = (item) => {
  if (!item) return null;
  const lat = parseFloat(item.lat ?? item.latitude ?? item.Latitude);
  const lon = parseFloat(item.lon ?? item.lng ?? item.longitude ?? item.Longitude);
  if (isNaN(lat) || isNaN(lon) || lat === null || lon === null) return null;
  return [lon, lat];
};

const safeUpper = (s) => (s ? String(s).toUpperCase() : "UNKNOWN");

const baseStyle = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [
    { id: "bg", type: "background", paint: { "background-color": "#EEF0F3" } },
    {
      id: "osm",
      type: "raster",
      source: "osm",
      paint: {
        "raster-opacity": 0.55,
        "raster-saturation": -0.75,
        "raster-brightness-min": 0.05,
        "raster-brightness-max": 1.0,
      },
    },
  ],
};

function createCircleCoordinates(lng, lat, radiusMeters, points = 64) {
  if (isNaN(lng) || isNaN(lat) || lng === null || lat === null || lng === undefined || lat === undefined) {
    return [[[0, 0], [0, 0], [0, 0], [0, 0]]];
  }
  const coords = [];
  const km = radiusMeters / 1000;
  for (let i = 0; i <= points; i++) {
    const angle = (i / points) * 2 * Math.PI;
    const dx = km * Math.cos(angle);
    const dy = km * Math.sin(angle);
    coords.push([lng + dx / (111.32 * Math.cos((lat * Math.PI) / 180)), lat + dy / 110.574]);
  }
  return [coords];
}

export default function NerMap({
  roads,
  vehicles = [],
  hazards = [],
  blockedEdges = [],
  alternativeRoutes = [],
  prePositioningRoutes = [],
  depots = [],
  villages = [],
  trafficOverlay = [],
  layers: layerProps = { roads: true, vehicles: true, incidents: true, traffic: false },
  onRoadClick,
  center,
  zoom,
  isDroppingPin,
  onMapClick,
  temporaryPin,
  zones,
  environment,
  incidents,
}) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const loadedRef = useRef(false);

  const layers = layerProps || { roads: true, vehicles: true, incidents: true, traffic: false };

  // DEBUG: shows if NerMap is mounting and what data it receives
  console.log("NerMap render", {
    hasContainer: !!containerRef.current,
    hasRoads: !!roads,
    vehiclesCount: vehicles?.length || 0,
    depotsCount: depots?.length || 0,
    villagesCount: villages?.length || 0,
    hazardsCount: hazards?.length || 0,
  });

  const markersRef = useRef({
    vehicles: [],
    hazards: [],
    depots: [],
    villages: [],
    tempPin: null
  });

  // Map initialization — runs once on mount
  useEffect(() => {
    if (!containerRef.current) {
      console.error("NerMap: container ref is null!");
      return;
    }

    const safeCenter = (center && !isNaN(center[0]) && !isNaN(center[1]))
      ? center
      : [91.88, 25.57];

    console.log("NerMap: initializing map with center", safeCenter);

    try {
      const map = new MLMap({
        container: containerRef.current,
        style: baseStyle,
        center: safeCenter,
        zoom: zoom || 6.2,
        attributionControl: { compact: true },
      });

      map.addControl(new NavigationControl({ showCompass: false }), "bottom-right");

      map.on("load", () => {
        console.log("NerMap: map loaded successfully");
        loadedRef.current = true;

        map.addSource("roads", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        map.addSource("blocked", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        map.addSource("alt_routes", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        map.addSource("pre_pos", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        map.addSource("hazard_zones", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        map.addSource("traffic", { type: "geojson", data: { type: "FeatureCollection", features: [] } });

        map.addLayer({
          id: "hazard-zones-fill", type: "fill", source: "hazard_zones",
          paint: { "fill-color": ["get", "color"], "fill-opacity": 0.15 }
        });
        map.addLayer({
          id: "hazard-zones-line", type: "line", source: "hazard_zones",
          paint: { "line-color": ["get", "color"], "line-width": 1, "line-dasharray": [2, 2] }
        });

        map.addLayer({
          id: "roads-line", type: "line", source: "roads",
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": [
              "match", ["get", "status"],
              "OPEN", STATUS_COLORS.OPEN,
              "AT_RISK", STATUS_COLORS.AT_RISK,
              "RESTRICTED", STATUS_COLORS.RESTRICTED,
              "BLOCKED", STATUS_COLORS.BLOCKED,
              "GOVERNMENT_CLOSED", STATUS_COLORS.GOVERNMENT_CLOSED,
              STATUS_COLORS.UNKNOWN,
            ],
            "line-width": ["interpolate", ["linear"], ["zoom"], 5, 2, 10, 4.5],
            "line-opacity": 0.8,
          },
        });

        map.addLayer({
          id: "blocked-line", type: "line", source: "blocked",
          layout: { "line-cap": "round", "line-join": "round" },
          paint: { "line-color": STATUS_COLORS.BLOCKED, "line-width": 5, "line-opacity": 0.9 }
        });

        map.addLayer({
          id: "alt-routes-line", type: "line", source: "alt_routes",
          layout: { "line-cap": "round", "line-join": "round" },
          paint: { "line-color": STATUS_COLORS.ALT_ROUTE, "line-width": 4, "line-opacity": 0.9 }
        });

        map.addLayer({
          id: "pre-pos-line", type: "line", source: "pre_pos",
          layout: { "line-cap": "round", "line-join": "round" },
          paint: { "line-color": STATUS_COLORS.PRE_POS, "line-width": 3, "line-dasharray": [2, 1], "line-opacity": 0.8 }
        });

        map.addLayer({
          id: "traffic-line", type: "line", source: "traffic",
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": ["get", "color"],
            "line-width": ["interpolate", ["linear"], ["zoom"], 5, 3, 10, 6],
            "line-opacity": 0.6
          }
        });

        map.on("click", "roads-line", (e) => {
          if (onRoadClick && e.features && e.features[0]) onRoadClick(e.features[0].properties);
        });
        map.on("mouseenter", "roads-line", () => { map.getCanvas().style.cursor = "pointer"; });
        map.on("mouseleave", "roads-line", () => { map.getCanvas().style.cursor = ""; });

        map.on("click", (e) => {
          if (isDroppingPin && onMapClick) {
            onMapClick({ lat: e.lngLat.lat, lon: e.lngLat.lng });
          }
        });
      });

      map.on("error", (e) => {
        console.error("NerMap: maplibre error", e);
      });

      mapRef.current = map;

      return () => {
        console.log("NerMap: cleaning up map");
        map.remove();
      };
    } catch (err) {
      console.error("NerMap: FAILED to initialize map", err);
    }
  }, []);

  // Update Sources
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;

    try {
      if (roads) map.getSource("roads").setData(roads);

      const blockedFC = {
        type: "FeatureCollection",
        features: (blockedEdges || []).filter(e => e && (e.matched_road_geometry || e.geometry)).map(e => ({
          type: "Feature", geometry: e.matched_road_geometry || e.geometry, properties: e
        }))
      };
      map.getSource("blocked").setData(blockedFC);

      const altFC = {
        type: "FeatureCollection",
        features: (alternativeRoutes || []).filter(r => r && r.geometry).map(r => ({
          type: "Feature", geometry: r.geometry, properties: r
        }))
      };
      map.getSource("alt_routes").setData(altFC);

      const prePosFC = {
        type: "FeatureCollection",
        features: (prePositioningRoutes || []).filter(r => r && r.geometry).map(r => ({
          type: "Feature", geometry: r.geometry, properties: r
        }))
      };
      map.getSource("pre_pos").setData(prePosFC);

      const hazardZonesFC = {
        type: "FeatureCollection",
        features: (hazards || []).map(h => {
          const coords = getCoords(h);
          if (!coords) return null;
          const colorKey = `${safeUpper(h.hazard_type)}_${safeUpper(h.source)}`;
          return {
            type: "Feature",
            geometry: { type: "Polygon", coordinates: createCircleCoordinates(coords[0], coords[1], h.hazard_radius_m || 500) },
            properties: { color: HAZARD_COLORS[colorKey] || "#888" }
          };
        }).filter(f => f !== null)
      };
      map.getSource("hazard_zones").setData(hazardZonesFC);

      if (layers.traffic) {
        const trafficFC = {
          type: "FeatureCollection",
          features: (trafficOverlay || []).filter(t => t && t.geometry).map(t => ({
            type: "Feature", geometry: t.geometry,
            properties: { color: t.speed > 40 ? "#16A34A" : t.speed > 20 ? "#EAB308" : "#DC2626" }
          }))
        };
        map.getSource("traffic").setData(trafficFC);
      } else {
        map.getSource("traffic").setData({ type: "FeatureCollection", features: [] });
      }
    } catch (err) {
      console.error("NerMap: error updating sources", err);
    }
  }, [roads, blockedEdges, alternativeRoutes, prePositioningRoutes, hazards, trafficOverlay, layers.traffic]);

  // Update Markers — ALL with NaN guards
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;

    try {
      Object.values(markersRef.current).forEach(m => {
        if (Array.isArray(m)) m.forEach(x => x && x.remove && x.remove());
        else if (m) m.remove && m.remove();
      });
      markersRef.current = { vehicles: [], hazards: [], depots: [], villages: [], tempPin: null };

      if (layers.vehicles) {
        (vehicles || []).forEach(v => {
          const coords = getCoords(v);
          if (!coords) return;

          const el = document.createElement("div");
          el.className = "vehicle-marker";
          const vType = (v.type || v.vehicle_type || "truck").toLowerCase();
          const color = vType === "ambulance" ? "#DC2626" : vType === "truck" ? "#2563EB" : vType.includes("supply") ? "#16A34A" : "#EA580C";
          el.style.cssText = `width:24px;height:24px;background:${color};border-radius:4px;border:2px solid #fff;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 4px rgba(0,0,0,0.3);cursor:pointer;`;
          el.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5"><path d="M12 2v20M2 12h20"/></svg>`;

          const govId = v.gov_id || v.government_id || v.id || "Unknown";
          const speed = v.speed || v.speed_kmh || 0;

          const marker = new Marker({ element: el }).setLngLat(coords).addTo(map);
          marker.getElement().addEventListener('click', () => {
            new Popup().setLngLat(coords)
              .setHTML(`<div class="p-2"><strong>${govId}</strong><br/>${vType}<br/>Speed: ${speed}km/h</div>`)
              .addTo(map);
          });
          markersRef.current.vehicles.push(marker);
        });
      }

      (hazards || []).forEach(h => {
        const coords = getCoords(h);
        if (!coords) return;

        const el = document.createElement("div");
        const colorKey = `${safeUpper(h.hazard_type)}_${safeUpper(h.source)}`;
        const color = HAZARD_COLORS[colorKey] || "#888";
        const isAI = h.source && (h.source.toLowerCase() === 'ai_prediction' || h.source.toLowerCase() === 'ai');
        el.style.cssText = `width:16px;height:16px;background:${color};border:2px solid #fff;transform:rotate(45deg);border-radius:2px;box-shadow:0 2px 4px rgba(0,0,0,0.3);${isAI ? 'border-style:dashed;' : ''}`;
        markersRef.current.hazards.push(new Marker({ element: el }).setLngLat(coords).addTo(map));
      });

      (depots || []).forEach(d => {
        const coords = getCoords(d);
        if (!coords) return;
        const el = document.createElement("div");
        el.style.cssText = "width:14px;height:14px;background:#1E40AF;border:2px solid #fff;box-shadow:0 2px 4px rgba(0,0,0,0.3);";
        markersRef.current.depots.push(new Marker({ element: el }).setLngLat(coords).addTo(map));
      });

      (villages || []).forEach(v => {
        const coords = getCoords(v);
        if (!coords) return;
        const el = document.createElement("div");
        el.style.cssText = "width:12px;height:12px;background:#15803D;border-radius:50%;border:2px solid #fff;box-shadow:0 2px 4px rgba(0,0,0,0.3);";
        markersRef.current.villages.push(new Marker({ element: el }).setLngLat(coords).addTo(map));
      });

      if (temporaryPin) {
        const coords = getCoords(temporaryPin);
        if (coords) {
          const el = document.createElement("div");
          el.style.cssText = "width:20px;height:20px;color:#2563EB;";
          el.innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>`;
          markersRef.current.tempPin = new Marker({ element: el }).setLngLat(coords).addTo(map);
        }
      }
    } catch (err) {
      console.error("NerMap: error updating markers", err);
    }
  }, [vehicles, hazards, depots, villages, temporaryPin, layers.vehicles]);

  useEffect(() => {
    if (mapRef.current) {
      mapRef.current.getCanvas().style.cursor = isDroppingPin ? "crosshair" : "";
    }
  }, [isDroppingPin]);

  return (
    <div className="relative w-full h-full" style={{ minHeight: '400px' }} data-testid="neris-map">
      <div ref={containerRef} className="absolute inset-0" style={{ height: "100%", width: "100%" }} />

      <div className="absolute bottom-4 right-4 bg-white/90 backdrop-blur-sm border rounded-lg p-3 shadow-sm text-[10px] space-y-2 pointer-events-none" data-testid="map-legend">
        <div className="font-bold uppercase tracking-wider text-neutral-500 mb-1">Legend</div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
          <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-sm" style={{ background: STATUS_COLORS.BLOCKED }} /><span>Blocked Road</span></div>
          <div className="flex items-center gap-2"><div className="w-3 h-[2px]" style={{ background: STATUS_COLORS.ALT_ROUTE }} /><span>Alt Route</span></div>
          <div className="flex items-center gap-2"><div className="w-3 h-[2px] border-b-2 border-dashed" style={{ borderColor: STATUS_COLORS.PRE_POS }} /><span>Pre-pos Plan</span></div>
          <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-sm bg-blue-600" /><span>Flood (Gov)</span></div>
          <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-sm bg-cyan-400 border border-dashed border-white" /><span>Flood (AI)</span></div>
          <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-sm bg-orange-600" /><span>Landslide (Gov)</span></div>
          <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-sm bg-yellow-500 border border-dashed border-white" /><span>Landslide (AI)</span></div>
          <div className="flex items-center gap-2"><div className="w-3 h-3 bg-blue-900" /><span>Depot</span></div>
          <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-green-700" /><span>Village</span></div>
        </div>
      </div>
    </div>
  );
}