import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { TrafficCone, Zap } from "lucide-react";
import { getTraffic } from "@/lib/pipelineApi";
import { useToast } from "@/hooks/use-toast";

export default function TrafficOverlay({ onToggle, onAvoidTraffic }) {
  const [enabled, setEnabled] = useState(false);
  const [loading, setLoading] = useState(false);
  const { toast } = useToast();

  const handleToggle = async (val) => {
    setEnabled(val);
    if (val) {
      setLoading(true);
      try {
        const data = await getTraffic();
        onToggle(true, data);
        toast({ title: "Traffic Live", description: "Real-time congestion data overlayed." });
      } catch (err) {
        toast({ title: "Error", description: "Failed to fetch traffic data.", variant: "destructive" });
        setEnabled(false);
      } finally {
        setLoading(false);
      }
    } else {
      onToggle(false, []);
    }
  };

  return (
    <div className="bg-white/95 backdrop-blur-sm border rounded-md shadow-sm p-2 flex items-center gap-3 pointer-events-auto">
      <div className="flex items-center gap-2 pr-2 border-r">
        <TrafficCone size={16} className={enabled ? "text-orange-500" : "text-neutral-400"} />
        <span className="text-[11px] font-bold uppercase tracking-wider text-neutral-600">Traffic</span>
        <Switch 
            checked={enabled} 
            onCheckedChange={handleToggle} 
            disabled={loading}
            className="data-[state=checked]:bg-orange-500"
        />
      </div>

      {enabled && (
          <div className="flex items-center gap-3 animate-in fade-in slide-in-from-left-2">
            <Badge variant="outline" className="text-[9px] bg-neutral-50 border-neutral-200 text-neutral-500 h-5">
                SOURCE: GOOGLE/OSM
            </Badge>
            <Button 
                size="sm" 
                variant="default" 
                className="h-6 text-[10px] bg-green-600 hover:bg-green-700 px-2 flex gap-1"
                onClick={onAvoidTraffic}
            >
                <Zap size={10} fill="currentColor" />
                Avoid Traffic
            </Button>
          </div>
      )}
    </div>
  );
}
