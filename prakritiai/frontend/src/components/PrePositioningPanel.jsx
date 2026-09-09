import { useState } from "react";
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { getAIPrediction } from "@/lib/pipelineApi";
import { CloudRain, Droplets, ShieldCheck, XCircle, TrendingDown, Info } from "lucide-react";

export default function PrePositioningPanel({ onPrediction }) {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [prediction, setPrediction] = useState(null);

  const simulateRainfall = async () => {
    setLoading(true);
    setPrediction(null);
    try {
      const params = {
        rainfall_24h: 150,
        rainfall_7d: 400,
        soil_moisture: 0.85,
        slope: 35,
        elevation: 1400,
        proximity_to_river: 300,
        historical_landslide_frequency: 7,
        historical_flood_frequency: 5,
      };
      // Umsaw Myllium (dep-shillong's seeded village) — inside the loaded
      // road network and has a real supply_routes document, so the backend
      // can actually resolve a named depot/village instead of falling back
      // to the nameless generic route hint.
      const res = await getAIPrediction(25.507, 91.8565, params);
      console.log("Rainfall prediction:", res);
      setPrediction(res);
      if (onPrediction) onPrediction(res);

      const prob = Math.max(res.flood_probability || 0, res.landslide_probability || 0);
      if (res.risk_level === "critical" || res.risk_level === "high") {
        toast({
          title: res.risk_level.toUpperCase() + " RISK",
          description: `${(prob * 100).toFixed(0)}% ${res.dominant_hazard} probability detected`,
          variant: "destructive",
        });
      } else {
        toast({ title: "Simulation Complete", description: `Risk level: ${res.risk_level}` });
      }
    } catch (err) {
      console.error("Rainfall simulation error:", err);
      toast({ title: "Simulation Failed", description: err.message || "Unknown error", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const simulateFlood = async () => {
    setLoading(true);
    setPrediction(null);
    try {
      const params = {
        rainfall_24h: 200,
        rainfall_7d: 500,
        soil_moisture: 0.9,
        slope: 8,
        elevation: 50,
        proximity_to_river: 100,
        historical_flood_frequency: 8,
        historical_landslide_frequency: 1,
      };
      const res = await getAIPrediction(25.507, 91.8565, params);
      console.log("Flood prediction:", res);
      setPrediction(res);
      if (onPrediction) onPrediction(res);

      const prob = Math.max(res.flood_probability || 0, res.landslide_probability || 0);
      if (res.risk_level === "critical" || res.risk_level === "high") {
        toast({
          title: res.risk_level.toUpperCase() + " RISK",
          description: `${(prob * 100).toFixed(0)}% ${res.dominant_hazard} probability detected`,
          variant: "destructive",
        });
      } else {
        toast({ title: "Simulation Complete", description: `Risk level: ${res.risk_level}` });
      }
    } catch (err) {
      console.error("Flood simulation error:", err);
      toast({ title: "Simulation Failed", description: err.message || "Unknown error", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const approveDispatch = () => {
    toast({ title: "Vehicles Dispatched", description: "Pre-positioning vehicles sent to village" });
    setPrediction(null);
  };

  // Use ACTUAL API response fields (not hardcoded)
  const probability = prediction
    ? Math.max(prediction.flood_probability || 0, prediction.landslide_probability || 0)
    : 0;

  // Convert commodities object to array for display
  const commoditiesArray = prediction?.pre_positioning_plan?.commodities
    ? Object.entries(prediction.pre_positioning_plan.commodities).map(([key, val]) => ({
        item: key,
        quantity: val,
        unit: "units",
      }))
    : [];

  // Use ACTUAL cost comparison from API
  const costData = prediction?.cost_comparison || null;

  // route_hint is either a real supply_routes doc (origin.name/destination.name
  // populated) when the coordinate matched a known route, or a nameless
  // generic fallback ({origin: {lat,lon}, note}) otherwise.
  const routeHint = prediction?.pre_positioning_plan?.route || null;
  const depotName = routeHint?.origin?.name || null;
  const villageName = routeHint?.destination?.name || null;

  return (
    <Card className="w-80 shadow-lg pointer-events-auto max-h-[90vh] overflow-y-auto">
      <CardHeader className="pb-3">
        <CardTitle className="text-lg flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-purple-600" />
          AI Pre-Positioning
        </CardTitle>
        <CardDescription>Predictive disaster risk & resource planning</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Simulate buttons */}
        <div className="grid grid-cols-2 gap-2">
          <Button variant="outline" size="sm" className="text-[10px] h-10 flex flex-col gap-0.5" onClick={simulateRainfall} disabled={loading}>
            <CloudRain size={14} className="text-blue-500" />
            Rainfall Risk
          </Button>
          <Button variant="outline" size="sm" className="text-[10px] h-10 flex flex-col gap-0.5" onClick={simulateFlood} disabled={loading}>
            <Droplets size={14} className="text-cyan-500" />
            Flood Risk
          </Button>
        </div>

        {/* Prediction result */}
        {prediction && (
          <div className="space-y-4">
            {/* Probability — uses ACTUAL API fields */}
            <div className="space-y-2">
              {prediction.route_criticality === "sole_route" && (
                <div className="bg-red-50 border border-red-200 text-red-700 text-[11px] p-2 rounded flex items-start gap-2">
                  <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                  <span className="font-semibold">{prediction.sole_route_alert}</span>
                </div>
              )}
              <div className="flex justify-between items-end">
                <span className="text-[11px] font-medium text-neutral-500">
                  {prediction.dominant_hazard?.toUpperCase()} Probability
                </span>
                <Badge variant={probability > 0.7 || prediction.route_criticality === "sole_route" ? "destructive" : "default"} className="text-[10px] h-4">
                  {(probability * 100).toFixed(0)}% {prediction.risk_level}
                </Badge>
              </div>
              <Progress value={probability * 100} className="h-1.5" />
              {/* Show BOTH probabilities */}
              <div className="flex justify-between text-[9px] text-neutral-400">
                <span>Flood: {((prediction.flood_probability || 0) * 100).toFixed(0)}%</span>
                <span>Landslide: {((prediction.landslide_probability || 0) * 100).toFixed(0)}%</span>
              </div>
            </div>

            {/* Pre-positioning plan — uses ACTUAL API fields */}
            {prediction.pre_positioning_recommended && prediction.pre_positioning_plan ? (
              <div className="space-y-3 pt-3 border-t">
                <div className="text-[11px] font-bold uppercase text-neutral-400 tracking-wider">Pre-Positioning Plan</div>

                {depotName && villageName ? (
                  <div className="flex items-center justify-between text-[12px] bg-neutral-50 p-2 rounded border">
                    <span className="font-semibold text-neutral-800">{depotName}</span>
                    <span className="text-neutral-400">&rarr;</span>
                    <span className="font-semibold text-neutral-800">{villageName}</span>
                  </div>
                ) : (
                  <div className="text-[11px] text-neutral-500 bg-neutral-50 p-2 rounded border">
                    {routeHint?.note || "No specific depot/village matched for this coordinate."}
                  </div>
                )}

                {/* Commodities — converted from object to array */}
                {commoditiesArray.length > 0 && (
                  <div className="space-y-2">
                    {commoditiesArray.map((c, i) => (
                      <div key={i} className="flex justify-between items-center text-[11px] bg-neutral-50 p-1.5 rounded border">
                        <span className="text-neutral-600 font-medium capitalize">{c.item}</span>
                        <span className="font-bold text-neutral-900">{c.quantity} {c.unit}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Vehicles needed */}
                {prediction.pre_positioning_plan.vehicles && (
                  <div className="flex justify-between items-center text-[11px] bg-blue-50 p-1.5 rounded border border-blue-100">
                    <span className="text-neutral-600 font-medium">Vehicles needed</span>
                    <span className="font-bold text-blue-900">{prediction.pre_positioning_plan.vehicles} truck(s)</span>
                  </div>
                )}

                {/* Cost comparison — uses ACTUAL values from API */}
                {costData && (
                  <div className="bg-purple-50 border border-purple-100 rounded-md p-2.5 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-bold text-purple-700 flex items-center gap-1">
                        <TrendingDown size={12} /> COST SAVINGS
                      </span>
                      <span className="text-[12px] font-black text-purple-800">
                        {costData.savings_pct?.toFixed(0)}%
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <div className="text-[9px] text-purple-400 uppercase">Pre-position</div>
                        <div className="text-[12px] font-bold text-purple-900">
                          ₹{(costData.pre_positioning_cost || 0).toLocaleString("en-IN")}
                        </div>
                      </div>
                      <div>
                        <div className="text-[9px] text-purple-400 uppercase">Emergency</div>
                        <div className="text-[12px] font-bold text-neutral-500 line-through">
                          ₹{(costData.emergency_transfer_cost || 0).toLocaleString("en-IN")}
                        </div>
                      </div>
                    </div>
                    <div className="text-[10px] text-purple-600 font-medium pt-1 border-t border-purple-100">
                      Savings: ₹{(costData.savings || 0).toLocaleString("en-IN")}
                    </div>
                  </div>
                )}

                {prediction.last_safe_departure && (
                  <div className={`p-2 rounded border text-[11px] ${prediction.last_safe_departure.status === 'TOO_LATE' ? 'bg-red-50 border-red-200 text-red-800' : 'bg-yellow-50 border-yellow-200 text-yellow-800'}`}>
                    <strong>Last Safe Departure:</strong> {prediction.last_safe_departure.minutes_remaining} mins remaining ({prediction.last_safe_departure.status})
                  </div>
                )}
                {prediction.confidence_action && (
                  <div className="p-2 bg-blue-50 border border-blue-200 text-blue-800 text-[11px] rounded">
                    <strong>AI Action:</strong> {prediction.confidence_action.action}<br/>
                    <span className="text-[9px] opacity-80">FP Cost: ₹{prediction.confidence_action.cost_false_positive.toLocaleString("en-IN")} | FN Cost: ₹{prediction.confidence_action.cost_false_negative.toLocaleString("en-IN")}</span>
                  </div>
                )}

                {/* Action buttons */}
                <div className="flex gap-2">
                  <Button size="sm" className="flex-1 h-8 text-[11px] bg-purple-600 hover:bg-purple-700" onClick={approveDispatch}>
                    Approve & Dispatch
                  </Button>
                  <Button size="sm" variant="ghost" className="h-8 w-8 p-0 text-neutral-400 hover:text-red-500" onClick={() => setPrediction(null)}>
                    <XCircle size={16} />
                  </Button>
                </div>
              </div>
            ) : (
              /* If no pre-positioning needed */
              <div className="bg-green-50 border border-green-100 rounded-md p-2.5 text-center">
                <div className="text-[11px] text-green-700 font-medium">
                  Risk level acceptable — no pre-positioning needed
                </div>
              </div>
            )}
          </div>
        )}

        {/* Empty state */}
        {!prediction && !loading && (
          <div className="flex flex-col items-center justify-center py-6 text-neutral-400 gap-2 text-center">
            <Info size={24} className="opacity-20" />
            <p className="text-[10px]">Run a simulation to generate AI-backed pre-positioning plans</p>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-6 gap-3">
            <div className="w-6 h-6 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
            <span className="text-[10px] text-neutral-500 font-medium animate-pulse">Running AI Model...</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}