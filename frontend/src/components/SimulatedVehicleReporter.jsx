import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Play, Square, Truck, Activity } from "lucide-react";
import { updateVehicleLocation } from "@/lib/pipelineApi";
import { useToast } from "@/hooks/use-toast";

export default function SimulatedVehicleReporter({ vehicles = [] }) {
  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState({}); // gov_id -> percentage
  const timerRef = useRef(null);
  const { toast } = useToast();

  const startSimulation = () => {
    setIsRunning(true);
    toast({ title: "Simulation Started", description: "Reporting live coordinates for active vehicles." });
  };

  const stopSimulation = () => {
    setIsRunning(false);
    if (timerRef.current) clearInterval(timerRef.current);
    toast({ title: "Simulation Stopped" });
  };

  useEffect(() => {
    if (isRunning && vehicles.length > 0) {
      timerRef.current = setInterval(() => {
        vehicles.forEach((v) => {
          // Simulate movement: Add small delta to lat/lon
          const dLat = (Math.random() - 0.5) * 0.001;
          const dLon = (Math.random() - 0.5) * 0.001;
          const speed = 30 + Math.random() * 30; // 30-60 km/h
          const heading = Math.random() * 360;

          updateVehicleLocation(v.gov_id, v.lat + dLat, v.lon + dLon, speed, heading)
            .catch(err => console.error(`Failed to update ${v.gov_id}:`, err));
          
          setProgress(prev => ({
              ...prev,
              [v.gov_id]: Math.min((prev[v.gov_id] || 0) + (Math.random() * 5), 100)
          }));
        });
      }, 5000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [isRunning, vehicles]);

  return (
    <Card className="w-80 shadow-lg pointer-events-auto">
      <CardHeader className="pb-3 border-b">
        <CardTitle className="text-[14px] flex items-center justify-between">
            <div className="flex items-center gap-2">
                <Activity size={16} className="text-green-500" />
                Live Simulation
            </div>
            {isRunning ? (
                <Badge variant="outline" className="text-[9px] bg-green-50 text-green-700 border-green-200 animate-pulse">ACTIVE</Badge>
            ) : (
                <Badge variant="outline" className="text-[9px] bg-neutral-50 text-neutral-400 border-neutral-200">IDLE</Badge>
            )}
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-4 space-y-4">
        <div className="flex gap-2">
            <Button 
                onClick={startSimulation} 
                disabled={isRunning} 
                size="sm" 
                className="flex-1 h-8 bg-green-600 hover:bg-green-700 text-[11px] gap-1.5"
            >
                <Play size={12} fill="currentColor" /> Start All
            </Button>
            <Button 
                onClick={stopSimulation} 
                disabled={!isRunning} 
                size="sm" 
                variant="outline"
                className="flex-1 h-8 text-[11px] gap-1.5"
            >
                <Square size={12} fill="currentColor" /> Stop All
            </Button>
        </div>

        <div className="space-y-3 max-h-48 overflow-y-auto pr-1">
            {vehicles.map(v => (
                <div key={v.gov_id} className="space-y-1.5">
                    <div className="flex justify-between items-center text-[10px]">
                        <span className="font-bold flex items-center gap-1">
                            <Truck size={10} className="text-blue-500" /> {v.gov_id}
                        </span>
                        <span className="text-neutral-400">{Math.round(progress[v.gov_id] || 0)}% Complete</span>
                    </div>
                    <Progress value={progress[v.gov_id] || 0} className="h-1" />
                </div>
            ))}
            {vehicles.length === 0 && (
                <div className="text-center py-4 text-[11px] text-neutral-400">No active vehicles to simulate</div>
            )}
        </div>
      </CardContent>
    </Card>
  );
}
