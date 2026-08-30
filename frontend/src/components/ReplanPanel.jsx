import { useState, useEffect } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useToast } from "@/hooks/use-toast";
import { getRoadNetwork, replanRoutes, injectHazard } from "@/lib/pipelineApi";
import { RefreshCw, AlertTriangle, Route as RouteIcon, Zap } from "lucide-react";

export default function ReplanPanel() {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [edges, setEdges] = useState([]);
  
  const [selectedEdge, setSelectedEdge] = useState("");
  const [blockagePct, setBlockagePct] = useState(0.95);
  const [hazardType, setHazardType] = useState("landslide");
  const [result, setResult] = useState(null);

  useEffect(() => {
    let mounted = true;
    const fetchEdges = async () => {
      try {
        const res = await getRoadNetwork(50);
        if (mounted && res.sample) {
          setEdges(res.sample);
          if (res.sample.length > 0) setSelectedEdge(res.sample[0].edge_id || res.sample[0].id || "");
        }
      } catch (err) {
        console.error("Failed to fetch roads for replan panel", err);
      }
    };
    fetchEdges();
    return () => { mounted = false; };
  }, []);

  const handleTestHazard = async () => {
    setLoading(true);
    try {
      toast({ title: "Injecting...", description: "Injecting test hazard at Shillong..." });
      const res = await injectHazard(25.5759, 91.8827, "landslide", "high", "Test injection");
      toast({ title: "Success", description: `Injected hazard. Edge ID: ${res.hazard_data.edge_id}` });
      // Add the edge to our list if not present so we can select it
      setEdges(prev => {
        const exists = prev.find(e => (e.edge_id || e.id) === res.hazard_data.edge_id);
        if (!exists) {
          return [{ edge_id: res.hazard_data.edge_id }, ...prev];
        }
        return prev;
      });
      setSelectedEdge(res.hazard_data.edge_id);
    } catch (err) {
      toast({ title: "Error", description: "Failed to inject test hazard.", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const handleReplan = async () => {
    if (!selectedEdge) {
      toast({ title: "Validation Error", description: "Please select an edge.", variant: "destructive" });
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const res = await replanRoutes(selectedEdge, blockagePct, hazardType);
      setResult(res);
      toast({ title: "Replan Complete", description: "Network re-optimized successfully." });
    } catch (err) {
      toast({ title: "Replan Failed", description: err.message, variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="w-[380px] shadow-lg shrink-0">
      <CardHeader className="pb-4 border-b">
        <div className="flex justify-between items-center">
          <CardTitle className="text-lg flex items-center gap-2">
            <RefreshCw className="w-5 h-5 text-indigo-500" />
            Real-time Replan
          </CardTitle>
          <Button variant="outline" size="sm" onClick={handleTestHazard} disabled={loading} className="h-7 text-xs bg-orange-50 text-orange-700 border-orange-200 hover:bg-orange-100">
            <Zap className="w-3 h-3 mr-1" /> Test Hazard
          </Button>
        </div>
      </CardHeader>
      <CardContent className="pt-4 space-y-4">
        <div className="space-y-1.5">
          <Label className="text-xs">Road Edge</Label>
          <Select value={selectedEdge} onValueChange={setSelectedEdge}>
            <SelectTrigger className="h-8 text-sm font-mono">
              <SelectValue placeholder="Select edge..." />
            </SelectTrigger>
            <SelectContent>
              {edges.map((e, i) => {
                const id = e.edge_id || e.id || `edge-${i}`;
                return <SelectItem key={id} value={id}>{id}</SelectItem>;
              })}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-3 pt-2">
          <div className="flex justify-between">
            <Label className="text-xs">Blockage Percentage</Label>
            <span className="text-xs font-mono">{(blockagePct * 100).toFixed(0)}%</span>
          </div>
          <Slider
            value={[blockagePct]}
            min={0.0}
            max={1.0}
            step={0.05}
            onValueChange={(v) => setBlockagePct(v[0])}
          />
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

        <Button onClick={handleReplan} disabled={loading} className="w-full h-8 text-sm mt-2 bg-indigo-600 hover:bg-indigo-700">
          {loading ? "Optimizing..." : "Trigger Replan"}
        </Button>

        {result && (
          <div className="mt-4 space-y-3">
            {result.total_blockade_check && (
              <Alert variant="destructive" className="py-2 px-3">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle className="text-xs uppercase mb-1">Total Blockade</AlertTitle>
                <AlertDescription className="text-xs">
                  {result.total_blockade_check}
                </AlertDescription>
              </Alert>
            )}

            <div className="p-3 bg-neutral-50 border rounded-md text-xs space-y-2">
              <div className="font-semibold text-neutral-800 border-b pb-1">Reoptimization Plan</div>
              {result.reoptimized_plan ? (
                <>
                  <div className="flex justify-between items-center">
                    <span className="text-neutral-500">Affected Routes</span>
                    <span className="font-mono">{result.reoptimized_plan.affected_routes?.length || 0}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-neutral-500">New Allocations</span>
                    <span className="font-mono">{result.reoptimized_plan.new_allocations?.length || 0}</span>
                  </div>
                </>
              ) : (
                <div className="text-neutral-500">Plan applied. Please verify on map.</div>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
