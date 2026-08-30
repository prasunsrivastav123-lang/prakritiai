import { useState, useEffect, useCallback } from "react";
import { ensureWS, subscribeWS } from "@/lib/ws";
import { getActiveVehicles } from "@/lib/pipelineApi";

export default function useVehicleTracking() {
  const [vehicles, setVehicles] = useState([]);
  const [activeVehicles, setActiveVehicles] = useState([]);
  const [hazards, setHazards] = useState([]);
  const [isConnected, setIsConnected] = useState(false);

  const fetchInitial = useCallback(async () => {
    try {
      const data = await getActiveVehicles();
      setActiveVehicles(data);
      setVehicles(data);
    } catch (err) {
      console.error("Failed to fetch active vehicles:", err);
    }
  }, []);

  useEffect(() => {
    fetchInitial();
    ensureWS();

    const unsub = subscribeWS((msg) => {
      setIsConnected(true);
      if (msg.type === "vehicle_location_update") {
        setVehicles((prev) => {
          const idx = prev.findIndex((v) => v.gov_id === msg.gov_id);
          if (idx > -1) {
            const next = [...prev];
            next[idx] = { ...next[idx], ...msg };
            return next;
          }
          return [...prev, msg];
        });
        setActiveVehicles((prev) => {
           const idx = prev.findIndex((v) => v.gov_id === msg.gov_id);
           if (idx > -1) {
             const next = [...prev];
             next[idx] = { ...next[idx], ...msg };
             return next;
           }
           return [...prev, msg];
        });
      } else if (msg.type === "hazard_injected") {
        setHazards((prev) => [...prev, msg.hazard_data]);
      } else if (msg.type === "ai_prediction") {
        if (msg.hazards) {
          setHazards((prev) => [...prev, ...msg.hazards]);
        }
      }
    });

    // Simple connection status check
    const checkStatus = setInterval(() => {
        // ws.js doesn't expose ws directly, so we infer from messages or just assume true if we got messages
        // For a real app, ws.js should probably expose state.
    }, 5000);

    return () => {
      unsub();
      clearInterval(checkStatus);
    };
  }, [fetchInitial]);

  return { vehicles, activeVehicles, hazards, isConnected, refresh: fetchInitial };
}
