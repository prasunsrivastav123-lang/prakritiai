import { useState } from "react";
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { injectAndOptimize } from "@/lib/pipelineApi";
import { MapPin, Navigation, AlertTriangle, Truck, Clock } from "lucide-react";

export default function HazardInjectionPanel({ isDroppingPin, setIsDroppingPin, pinCoords }) {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [lat, setLat] = useState("25.5759");
  const [lon, setLon] = useState("91.8827");
  const [hazardType, setHazardType] = useState("flood");
  const [severity, setSeverity] = useState("high");
  const [source, setSource] = useState("government");
  const [notes, setNotes] = useState("");
  const [result, setResult] = useState(null);

  // Auto-update inputs when a pin is dropped
  if (pinCoords && (pinCoords.lat?.toString() !== lat || pinCoords.lon?.toString() !== lon)) {
    setLat(pinCoords.lat?.toString() || "");
    setLon(pinCoords.lon?.toString() || "");
  }

  const handleUseMyLocation = () => {
    if (!navigator.geolocation) {
      toast({ title: "Error", description: "Geolocation not supported.", variant: "destructive" });
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLat(pos.coords.latitude.toFixed(6));
        setLon(pos.coords.longitude.toFixed(6));
        toast({ title: "Location acquired", description: "Coordinates updated." });
      },
      () => { toast({ title: "Error", description: "Failed to get location.", variant: "destructive" }); }
    );
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!lat || !lon) {
      toast({ title: "Validation Error", description: "Latitude and Longitude required.", variant: "destructive" });
      return;
    }

    setLoading(true);
    setResult(null);
    try {
      // FIXED: source is now "government" or "ai_prediction" (lowercase)
      const res = await injectAndOptimize(parseFloat(lat), parseFloat(lon), hazardType, severity, notes, source);
      console.log("Inject result in component:", res);
      setResult(res);

      if (res.matched_road) {
        toast({ title: "Hazard Injected", description: `Road ${res.matched_road.edge_id} BLOCKED. Distance: ${res.matched_road.distance_from_hazard_m}m` });
      } else {
        toast({ title: "Hazard Recorded", description: "No road found within 500m." });
      }

      if (isDroppingPin) setIsDroppingPin(false);
    } catch (err) {
      console.error("Inject error in component:", err);
      toast({ title: "Error", description: err.message || "Failed to inject hazard.", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="w-80 shadow-lg pointer-events-auto max-h-[90vh] overflow-y-auto">
      <CardHeader className="pb-4">
        <CardTitle className="text-lg flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-orange-500" />
          Inject Hazard
        </CardTitle>
        <CardDescription>Report hazard & trigger auto-optimization</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Source */}
          <div className="space-y-1.5">
            <Label className="text-xs">Reporting Source</Label>
            <Select value={source} onValueChange={setSource}>
              <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="government">Government Agency</SelectItem>
                <SelectItem value="ai_prediction">AI Prediction</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Coordinates */}
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Latitude</Label>
              <Input value={lat} onChange={(e) => setLat(e.target.value)} placeholder="25.5759" className="h-8 text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Longitude</Label>
              <Input value={lon} onChange={(e) => setLon(e.target.value)} placeholder="91.8827" className="h-8 text-sm" />
            </div>
          </div>

          {/* Buttons */}
          <div className="flex gap-2">
            <Button type="button" variant="outline" size="sm" className="flex-1 text-xs h-8" onClick={handleUseMyLocation}>
              <Navigation className="w-3 h-3 mr-1" /> My Location
            </Button>
            <Button
              type="button"
              variant={isDroppingPin ? "default" : "outline"}
              size="sm"
              className={`flex-1 text-xs h-8 ${isDroppingPin ? "bg-blue-600 text-white" : ""}`}
              onClick={() => setIsDroppingPin(!isDroppingPin)}
            >
              <MapPin className="w-3 h-3 mr-1" /> {isDroppingPin ? "Click Map..." : "Drop Pin"}
            </Button>
          </div>

          {/* Hazard Type */}
          <div className="space-y-1.5">
            <Label className="text-xs">Hazard Type</Label>
            <Select value={hazardType} onValueChange={setHazardType}>
              <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="flood">Flood</SelectItem>
                <SelectItem value="landslide">Landslide</SelectItem>
                <SelectItem value="road_damage">Road Damage</SelectItem>
                <SelectItem value="closure">Closure</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Severity */}
          <div className="space-y-1.5">
            <Label className="text-xs">Severity</Label>
            <Select value={severity} onValueChange={setSeverity}>
              <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="low">Low</SelectItem>
                <SelectItem value="medium">Medium</SelectItem>
                <SelectItem value="high">High</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <Button type="submit" disabled={loading} className="w-full h-8 text-sm mt-2">
            {loading ? "Analyzing..." : "Inject & Optimize"}
          </Button>
        </form>

        {/* Result — FIXED: uses correct API field names */}
        {result && (
          <div className="mt-4 p-3 bg-neutral-50 rounded-md border text-[11px] space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="font-bold uppercase text-[9px] text-neutral-500 tracking-wider">Analysis Result</span>
              <Badge variant={result.matched_road ? "destructive" : "warning"} className="text-[9px] px-1.5 py-0">
                {result.matched_road ? "BLOCKED" : "NO ROAD"}
              </Badge>
            </div>

            <div className="space-y-1 text-neutral-600">
              {/* FIXED: result.hazard not result.hazard_data */}
              {result.matched_road && (
                <div className="flex justify-between">
                  <span>Nearest Road</span>
                  <span className="font-mono text-blue-600 font-semibold">{result.matched_road.edge_id}</span>
                </div>
              )}
              {result.matched_road && (
                <div className="flex justify-between">
                  <span>Distance</span>
                  <span className="font-semibold text-neutral-900">{result.matched_road.distance_from_hazard_m?.toFixed(1)}m</span>
                </div>
              )}
              {/* FIXED: result.affected_villages (already correct) */}
              <div className="flex justify-between">
                <span>Affected Villages</span>
                <span className="font-semibold text-neutral-900">{result.affected_villages?.length || 0}</span>
              </div>
              {/* FIXED: result.alternative_routes not result.alternative_route */}
              <div className="flex justify-between">
                <span>Alt Routes Found</span>
                <span className={result.alternative_routes?.length > 0 ? "text-green-600 font-semibold" : "text-neutral-400"}>
                  {result.alternative_routes?.length || 0}
                </span>
              </div>
              {/* FIXED: result.affected_vehicles */}
              <div className="flex justify-between">
                <span>Vehicles Rerouted</span>
                <span className="font-semibold text-neutral-900">{result.affected_vehicles?.length || 0}</span>
              </div>
            </div>

            {/* Detailed Supply Suggestions (LP Allocation) */}
            {result.optimal_allocation && Array.isArray(result.optimal_allocation) && (
              <div className="pt-2 border-t space-y-2 mt-2">
                <div className="flex items-center gap-1.5 text-neutral-900 font-semibold mb-1">
                  <Truck size={12} className="text-blue-600" /> Supply Suggestions (Depot → Village)
                </div>
                
                <div className="max-h-32 overflow-y-auto rounded border">
                  <table className="w-full text-[10px] text-left">
                    <thead className="bg-neutral-100 text-neutral-500 sticky top-0">
                      <tr>
                        <th className="p-1 font-medium border-b">From Depot</th>
                        <th className="p-1 font-medium border-b">To Village</th>
                        <th className="p-1 font-medium border-b">Commodity</th>
                        <th className="p-1 font-medium border-b text-right">Qty</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y text-neutral-700 bg-white">
                      {result.optimal_allocation.length === 0 ? (
                        <tr><td colSpan={4} className="text-center p-2 text-neutral-400">No safe routes available to shift commodities.</td></tr>
                      ) : (
                        result.optimal_allocation.map((alloc, idx) => (
                          <tr key={idx} className="hover:bg-blue-50/50">
                            <td className="p-1 font-medium text-blue-700">{alloc.depot_id || alloc.depot}</td>
                            <td className="p-1">{alloc.village_id || alloc.village}</td>
                            <td className="p-1 capitalize">{alloc.commodity}</td>
                            <td className="p-1 text-right font-mono font-semibold">{alloc.quantity || alloc.qty}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>

                <div className="grid grid-cols-2 gap-2 text-neutral-600 mt-2">
                  <div className="bg-white border rounded p-1.5 shadow-sm">
                    <div className="text-[9px] text-neutral-400 uppercase tracking-wider">Vehicles Needed</div>
                    <div className="text-[13px] font-bold text-neutral-800">{result.vehicles_needed || 0}</div>
                  </div>
                  <div className="bg-white border rounded p-1.5 shadow-sm">
                    <div className="text-[9px] text-neutral-400 uppercase tracking-wider">Est. Cost</div>
                    <div className="text-[13px] font-bold text-neutral-800">₹{(result.estimated_cost || 0).toLocaleString('en-IN')}</div>
                  </div>
                </div>

                {result.vehicles_needed > 0 && (
                  <Button size="sm" className="w-full h-8 text-[11px] mt-1 bg-blue-600 hover:bg-blue-700 shadow-sm"
                    onClick={() => toast({ title: "Vehicles Dispatched", description: `${result.vehicles_needed} truck(s) dispatched along optimized routes.` })}>
                    <Navigation className="w-3 h-3 mr-1" /> Shift Commodities via Optimized Routes
                  </Button>
                )}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
