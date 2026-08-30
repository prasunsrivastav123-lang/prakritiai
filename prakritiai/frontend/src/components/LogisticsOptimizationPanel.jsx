import { useState } from "react";
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/hooks/use-toast";
import { optimizeLogistics, orchestratePipeline } from "@/lib/pipelineApi";
import { Boxes, Play, Plus, Trash2 } from "lucide-react";

export default function LogisticsOptimizationPanel() {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("depots");

  const [depots, setDepots] = useState([{ id: "D1", lat: 26.1, lon: 91.7, inventory: { food: 1000, water: 2000 } }]);
  const [villages, setVillages] = useState([{ id: "V1", lat: 25.5, lon: 91.8, demand: { food: 500, water: 800 } }]);
  const [commodities, setCommodities] = useState("food, water, medicine");
  const [results, setResults] = useState(null);

  const handleOptimize = async () => {
    setLoading(true);
    try {
      const comms = commodities.split(",").map(c => c.trim()).filter(Boolean);
      const inventory = {};
      depots.forEach(d => inventory[d.id] = d.inventory);
      
      const demand = {};
      villages.forEach(v => demand[v.id] = v.demand);

      const res = await optimizeLogistics(
        depots.map(({ id, lat, lon }) => ({ id, lat, lon })),
        villages.map(({ id, lat, lon }) => ({ id, lat, lon })),
        inventory,
        demand,
        comms
      );
      setResults(res.allocation);
      toast({ title: "Optimization Complete", description: "Allocations have been generated." });
    } catch (err) {
      toast({ title: "Optimization Failed", description: err.message, variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const handleOrchestrate = async () => {
    setLoading(true);
    try {
      const comms = commodities.split(",").map(c => c.trim()).filter(Boolean);
      const inventory = {};
      depots.forEach(d => inventory[d.id] = d.inventory);
      const demand = {};
      villages.forEach(v => demand[v.id] = v.demand);

      await orchestratePipeline(
        depots.map(({ id, lat, lon }) => ({ id, lat, lon })),
        villages.map(({ id, lat, lon }) => ({ id, lat, lon })),
        inventory,
        demand,
        comms
      );
      toast({ title: "Pipeline Orchestrated", description: "Full end-to-end run completed." });
    } catch (err) {
      toast({ title: "Pipeline Failed", description: err.message, variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="w-full max-w-4xl shadow-md border bg-white">
      <CardHeader>
        <CardTitle className="text-xl flex items-center gap-2 text-neutral-800">
          <Boxes className="w-6 h-6 text-indigo-600" />
          Logistics & Allocation LP
        </CardTitle>
        <CardDescription>Optimize supply distribution from depots to affected villages over the road network.</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Commodities (comma separated)</Label>
              <Input value={commodities} onChange={e => setCommodities(e.target.value)} placeholder="food, water, medicine" />
            </div>

            <div className="flex gap-2">
              <Button onClick={() => setActiveTab("depots")} variant={activeTab === "depots" ? "default" : "outline"} size="sm" className="flex-1">Depots</Button>
              <Button onClick={() => setActiveTab("villages")} variant={activeTab === "villages" ? "default" : "outline"} size="sm" className="flex-1">Villages</Button>
            </div>

            <div className="p-3 border rounded-md bg-neutral-50 min-h-[200px]">
              {activeTab === "depots" && (
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="font-semibold text-sm">Depots ({depots.length})</span>
                    <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={() => setDepots([...depots, { id: `D${depots.length + 1}`, lat: 0, lon: 0, inventory: {} }])}>
                      <Plus className="w-3 h-3 mr-1" /> Add
                    </Button>
                  </div>
                  {depots.map((d, i) => (
                    <div key={i} className="flex gap-2 items-center bg-white p-2 border rounded-md">
                      <Input value={d.id} className="w-16 h-7 text-xs" readOnly />
                      <div className="text-xs text-neutral-500 truncate w-32">Inventory set</div>
                      <div className="flex-1"></div>
                      <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-red-500 hover:text-red-700" onClick={() => setDepots(depots.filter((_, idx) => idx !== i))}>
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
              {activeTab === "villages" && (
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="font-semibold text-sm">Villages ({villages.length})</span>
                    <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={() => setVillages([...villages, { id: `V${villages.length + 1}`, lat: 0, lon: 0, demand: {} }])}>
                      <Plus className="w-3 h-3 mr-1" /> Add
                    </Button>
                  </div>
                  {villages.map((v, i) => (
                    <div key={i} className="flex gap-2 items-center bg-white p-2 border rounded-md">
                      <Input value={v.id} className="w-16 h-7 text-xs" readOnly />
                      <div className="text-xs text-neutral-500 truncate w-32">Demand set</div>
                      <div className="flex-1"></div>
                      <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-red-500 hover:text-red-700" onClick={() => setVillages(villages.filter((_, idx) => idx !== i))}>
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="flex gap-3">
              <Button onClick={handleOptimize} disabled={loading} className="flex-1 bg-indigo-600 hover:bg-indigo-700">
                Optimize Allocation
              </Button>
              <Button onClick={handleOrchestrate} disabled={loading} variant="outline" className="flex-1">
                <Play className="w-4 h-4 mr-2" /> Run Full Pipeline
              </Button>
            </div>
          </div>

          <div className="border rounded-md overflow-hidden bg-white flex flex-col">
            <div className="bg-neutral-100 p-2 text-sm font-semibold border-b">
              Results
            </div>
            <div className="p-0 flex-1 overflow-auto max-h-[350px]">
              {!results ? (
                <div className="h-full flex items-center justify-center text-neutral-400 text-sm p-8">
                  Click 'Optimize Allocation' to generate results.
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Depot</TableHead>
                      <TableHead>Village</TableHead>
                      <TableHead>Commodity</TableHead>
                      <TableHead className="text-right">Qty</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {results.length === 0 ? (
                      <TableRow><TableCell colSpan={4} className="text-center">No allocations possible.</TableCell></TableRow>
                    ) : (
                      results.map((r, i) => (
                        <TableRow key={i}>
                          <TableCell className="font-medium">{r.depot_id || r.depot}</TableCell>
                          <TableCell>{r.village_id || r.village}</TableCell>
                          <TableCell>{r.commodity}</TableCell>
                          <TableCell className="text-right font-mono">{r.quantity || r.qty || r.amount}</TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              )}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
