import { useState } from "react";
import { Card, CardHeader, CardTitle, CardContent, CardDescription, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { injectHazard } from "@/lib/pipelineApi";
import { MapPin, Navigation, AlertTriangle } from "lucide-react";

export default function HazardInjectionPanel({ isDroppingPin, setIsDroppingPin, pinCoords }) {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [hazardType, setHazardType] = useState("landslide");
  const [severity, setSeverity] = useState("medium");
  const [notes, setNotes] = useState("");
  const [result, setResult] = useState(null);

  // Auto-update inputs when a pin is dropped
  if (pinCoords && (pinCoords.lat.toString() !== lat || pinCoords.lon.toString() !== lon)) {
    setLat(pinCoords.lat.toString());
    setLon(pinCoords.lon.toString());
  }

  const handleUseMyLocation = () => {
    if (!navigator.geolocation) {
      toast({ title: "Error", description: "Geolocation is not supported by your browser.", variant: "destructive" });
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLat(pos.coords.latitude.toFixed(6));
        setLon(pos.coords.longitude.toFixed(6));
        toast({ title: "Location acquired", description: "Coordinates updated." });
      },
      () => {
        toast({ title: "Error", description: "Failed to get location.", variant: "destructive" });
      }
    );
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!lat || !lon) {
      toast({ title: "Validation Error", description: "Latitude and Longitude are required.", variant: "destructive" });
      return;
    }

    setLoading(true);
    setResult(null);
    try {
      const res = await injectHazard(parseFloat(lat), parseFloat(lon), hazardType, severity, notes);
      setResult(res.hazard_data);
      toast({ title: "Success", description: "Hazard injected successfully." });
      if (isDroppingPin) setIsDroppingPin(false);
    } catch (err) {
      toast({ title: "Error", description: err.message || "Failed to inject hazard.", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="w-80 shadow-lg pointer-events-auto">
      <CardHeader className="pb-4">
        <CardTitle className="text-lg flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-orange-500" />
          Inject Hazard
        </CardTitle>
        <CardDescription>Manually report a new hazard</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Latitude</Label>
              <Input
                value={lat}
                onChange={(e) => setLat(e.target.value)}
                placeholder="25.5759"
                className="h-8 text-sm"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Longitude</Label>
              <Input
                value={lon}
                onChange={(e) => setLon(e.target.value)}
                placeholder="91.8827"
                className="h-8 text-sm"
              />
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="flex-1 text-xs h-8"
              onClick={handleUseMyLocation}
            >
              <Navigation className="w-3 h-3 mr-1" /> My Location
            </Button>
            <Button
              type="button"
              variant={isDroppingPin ? "default" : "outline"}
              size="sm"
              className={`flex-1 text-xs h-8 ${isDroppingPin ? "bg-blue-600 text-white hover:bg-blue-700" : ""}`}
              onClick={() => setIsDroppingPin(!isDroppingPin)}
            >
              <MapPin className="w-3 h-3 mr-1" /> {isDroppingPin ? "Click Map..." : "Drop Pin"}
            </Button>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Hazard Type</Label>
            <Select value={hazardType} onValueChange={setHazardType}>
              <SelectTrigger className="h-8 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="landslide">Landslide</SelectItem>
                <SelectItem value="flood">Flood</SelectItem>
                <SelectItem value="road_damage">Road Damage</SelectItem>
                <SelectItem value="closure">Closure</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Severity</Label>
            <Select value={severity} onValueChange={setSeverity}>
              <SelectTrigger className="h-8 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="low">Low</SelectItem>
                <SelectItem value="medium">Medium</SelectItem>
                <SelectItem value="high">High</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Notes (Optional)</Label>
            <Input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. road fully blocked"
              className="h-8 text-sm"
            />
          </div>

          <Button type="submit" disabled={loading} className="w-full h-8 text-sm mt-2">
            {loading ? "Injecting..." : "Inject Hazard"}
          </Button>
        </form>

        {result && (
          <div className="mt-4 p-3 bg-neutral-50 rounded-md border text-xs space-y-1.5">
            <div className="font-semibold mb-1">Result</div>
            <div className="flex justify-between">
              <span className="text-neutral-500">Edge ID</span>
              <span className="font-mono text-[10px]">{result.edge_id}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-neutral-500">Blockage</span>
              <span>{(result.blockage_pct * 100).toFixed(0)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-neutral-500">Est. Clearance</span>
              <span>{result.est_clearance_hrs} hrs</span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
