import { useEffect, useState } from "react";
import { getPipelineStatus } from "@/lib/pipelineApi";
import { Badge } from "@/components/ui/badge";
import { Activity, ServerCrash } from "lucide-react";

export default function PipelineStatusWidget() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let mounted = true;
    const fetchStatus = async () => {
      try {
        const data = await getPipelineStatus();
        if (mounted) {
          setStatus(data);
          setError(false);
        }
      } catch (err) {
        if (mounted) {
          setError(true);
        }
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 30000); // 30 seconds
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  if (error) {
    return (
      <div className="flex items-center gap-2 bg-white px-3 py-1.5 rounded-full border shadow-sm text-xs font-medium text-neutral-600 pointer-events-auto">
        <span>Pipeline:</span>
        <Badge variant="destructive" className="h-5 px-1.5 flex gap-1">
          <ServerCrash className="w-3 h-3" /> Error
        </Badge>
      </div>
    );
  }

  if (!status) {
    return (
      <div className="flex items-center gap-2 bg-white px-3 py-1.5 rounded-full border shadow-sm text-xs font-medium text-neutral-600 pointer-events-auto">
        <span>Pipeline:</span>
        <Badge variant="outline" className="h-5 px-1.5 text-neutral-500 bg-neutral-100">
          Loading...
        </Badge>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3 bg-white px-3 py-1.5 rounded-full border shadow-sm text-xs font-medium text-neutral-600 pointer-events-auto">
      <div className="flex items-center gap-1.5">
        <span>Pipeline:</span>
        <Badge className="bg-green-600 hover:bg-green-700 h-5 px-1.5 flex gap-1 text-white border-transparent">
          <Activity className="w-3 h-3" /> Operational
        </Badge>
      </div>
      <div className="w-px h-4 bg-neutral-200"></div>
      <div className="flex gap-3 text-neutral-500" title="Network Size">
        <span>🛣️ {status.road_network?.total_edges?.toLocaleString() || 0}</span>
        <span>⚠️ {status.hazards?.total_records?.toLocaleString() || 0}</span>
      </div>
    </div>
  );
}
