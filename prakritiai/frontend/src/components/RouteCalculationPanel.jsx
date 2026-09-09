import { useState } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from "@/components/ui/collapsible";
import { useToast } from "@/hooks/use-toast";
import { calculateRoute } from "@/lib/pipelineApi";
import { Route as RouteIcon, Navigation, MapPin, ChevronDown } from "lucide-react";

export default function RouteCalculationPanel({ onRouteCalculated }) {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  // Defaults: Shillong Central Depot -> Umsaw Myllium — both inside the
  // loaded ~12km Shillong road network (the old destination, Guwahati, was
  // ~65km outside it, so "Find Route" could never find a road to snap to).
  const [originLat, setOriginLat] = useState("25.5759");
  const [originLon, setOriginLon] = useState("91.8827");
  const [destLat, setDestLat] = useState("25.507");
  const [destLon, setDestLon] = useState("91.8565");
  const [minSurvivability, setMinSurvivability] = useState(0.85);
  const [kPaths, setKPaths] = useState(3);
  const [result, setResult] = useState(null);

  const handleUseMyLocation = () => {
    if (!navigator.geolocation) {
      toast({ title: "Error", description: "Geolocation is not supported.", variant: "destructive" });
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setOriginLat(pos.coords.latitude.toFixed(6));
        setOriginLon(pos.coords.longitude.toFixed(6));
        toast({ title: "Location acquired", description: "Origin updated." });
      },
      () => toast({ title: "Error", description: "Failed to get location.", variant: "destructive" })
    );
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setResult(null);
    try {
      const res = await calculateRoute(
        parseFloat(originLat),
        parseFloat(originLon),
        parseFloat(destLat),
        parseFloat(destLon),
        minSurvivability,
        parseInt(kPaths, 10)
      );
      setResult(res);
      toast({ title: "Success", description: "Route calculated successfully." });
      if (onRouteCalculated && res.best_route && res.best_route.path) {
        // Pass the full response (not just best_route) so the map has the
        // origin/destination coordinates for endpoint markers too.
        onRouteCalculated(res);
      }
    } catch (err) {
      toast({ title: "Error", description: err.message || "Failed to calculate route.", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="w-[340px] shadow-lg pointer-events-auto shrink-0 h-fit">
      <CardHeader className="pb-4">
        <CardTitle className="text-lg flex items-center gap-2">
          <RouteIcon className="w-5 h-5 text-blue-500" />
          Route Calculation
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <div className="flex justify-between items-center">
              <Label className="text-xs font-semibold text-neutral-700">Origin</Label>
              <Button type="button" variant="ghost" size="sm" className="h-6 px-2 text-[10px]" onClick={handleUseMyLocation}>
                <Navigation className="w-3 h-3 mr-1" /> My Location
              </Button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Input value={originLat} onChange={(e) => setOriginLat(e.target.value)} placeholder="Lat" className="h-8 text-sm" />
              <Input value={originLon} onChange={(e) => setOriginLon(e.target.value)} placeholder="Lon" className="h-8 text-sm" />
            </div>
          </div>

          <div className="space-y-2">
            <Label className="text-xs font-semibold text-neutral-700">Destination</Label>
            <div className="grid grid-cols-2 gap-2">
              <Input value={destLat} onChange={(e) => setDestLat(e.target.value)} placeholder="Lat" className="h-8 text-sm" />
              <Input value={destLon} onChange={(e) => setDestLon(e.target.value)} placeholder="Lon" className="h-8 text-sm" />
            </div>
          </div>

          <div className="space-y-3 pt-2">
            <div className="flex justify-between">
              <Label className="text-xs">Min Survivability</Label>
              <span className="text-xs font-mono">{minSurvivability.toFixed(2)}</span>
            </div>
            <Slider
              value={[minSurvivability]}
              min={0.5}
              max={1.0}
              step={0.05}
              onValueChange={(v) => setMinSurvivability(v[0])}
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Alternative Routes (K)</Label>
            <Input
              type="number"
              min={1}
              max={5}
              value={kPaths}
              onChange={(e) => setKPaths(e.target.value)}
              className="h-8 text-sm"
            />
          </div>

          <Button type="submit" disabled={loading} className="w-full h-8 text-sm">
            {loading ? "Calculating..." : "Find Route"}
          </Button>
        </form>

        {result && result.best_route && (
          <div className="mt-4 space-y-2">
            <div className="p-3 bg-green-50 rounded-md border border-green-200 text-xs space-y-1.5">
              <div className="font-semibold text-green-800 mb-1">Best Route</div>
              <div className="flex justify-between">
                <span className="text-neutral-600">Survivability</span>
                <span className="font-semibold text-green-700">{(result.best_route.survivability * 100).toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-600">Travel Time</span>
                <span>{result.best_route.travel_time?.toFixed(1) || 0} hrs</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-600">Path Length</span>
                <span>{result.best_route.path?.length || 0} edges</span>
              </div>
            </div>

            {result.alternative_routes && result.alternative_routes.length > 0 && (
              <Collapsible>
                <CollapsibleTrigger className="flex items-center justify-between w-full p-2 bg-neutral-50 border rounded-md text-xs font-medium hover:bg-neutral-100">
                  Alternative Routes ({result.alternative_routes.length})
                  <ChevronDown className="w-4 h-4" />
                </CollapsibleTrigger>
                <CollapsibleContent className="space-y-2 mt-2">
                  {result.alternative_routes.map((alt, idx) => (
                    <div key={idx} className="p-2 bg-white border rounded-md text-xs space-y-1">
                      <div className="flex justify-between">
                        <span className="font-medium text-neutral-700">Route #{idx + 2}</span>
                        <span className="text-orange-600 font-semibold">{(alt.survivability * 100).toFixed(1)}%</span>
                      </div>
                      <div className="text-neutral-500 text-[10px]">Time: {alt.travel_time?.toFixed(1)} hrs | {alt.path?.length} edges</div>
                    </div>
                  ))}
                </CollapsibleContent>
              </Collapsible>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
