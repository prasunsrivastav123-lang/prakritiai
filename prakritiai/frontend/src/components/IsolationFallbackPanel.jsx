import { Card, CardHeader, CardTitle, CardContent, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { AlertOctagon } from "lucide-react";

const MODE_COLOR = { track: "#78716C", drone: "#0EA5E9", helicopter: "#7C3AED" };
const MODE_LABEL = { track: "Track / 2-Wheeler", drone: "Drone", helicopter: "Helicopter" };

export default function IsolationFallbackPanel({ villages = [], fallbackOptions = {} }) {
  const { toast } = useToast();
  const villageById = Object.fromEntries((villages || []).map((v) => [v.id, v]));
  const entries = Object.entries(fallbackOptions || {});

  if (entries.length === 0) return null;

  return (
    <Card className="w-80 shadow-lg pointer-events-auto max-h-[90vh] overflow-y-auto">
      <CardHeader className="pb-4">
        <CardTitle className="text-lg flex items-center gap-2">
          <AlertOctagon className="w-5 h-5 text-red-600" />
          Isolated Village Fallback
        </CardTitle>
        <CardDescription>No vehicle route survives — ranked delivery alternatives</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {entries.map(([villageId, byCommodity]) => {
          const vil = villageById[villageId];
          return (
            <div key={villageId} className="p-3 bg-neutral-50 rounded-md border text-[11px] space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="font-bold text-neutral-800">{vil?.name || villageId}</span>
                <Badge variant="destructive" className="text-[9px] px-1.5 py-0">ISOLATED</Badge>
              </div>

              {Object.entries(byCommodity).map(([commodity, { ranked, recommended }]) => (
                <div key={commodity} className="space-y-1">
                  <div className="font-semibold uppercase text-[9px] text-neutral-500 tracking-wider">{commodity}</div>
                  <div className="space-y-1">
                    {ranked.map((opt) => {
                      const isRecommended = opt.mode === recommended;
                      return (
                        <div
                          key={opt.mode}
                          className={`flex items-center justify-between px-2 py-1 rounded border ${
                            isRecommended ? "bg-white border-l-4" : "bg-white/60 border-neutral-100 opacity-70"
                          }`}
                          style={isRecommended ? { borderLeftColor: MODE_COLOR[opt.mode] } : undefined}
                        >
                          <div className="flex items-center gap-1.5">
                            <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: MODE_COLOR[opt.mode] }} />
                            <span className="text-neutral-700">{MODE_LABEL[opt.mode] || opt.mode}</span>
                            {isRecommended && <Badge className="text-[8px] px-1 py-0 bg-emerald-600">BEST</Badge>}
                          </div>
                          <div className="text-right">
                            {opt.feasible ? (
                              <span className="font-mono font-semibold text-neutral-800">₹{opt.cost} · {opt.eta_hours}h</span>
                            ) : (
                              <span className="text-neutral-400 text-[10px]" title={opt.reason}>infeasible</span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}

              {hasRecommendedOption(byCommodity) && (
                <Button
                  size="sm"
                  className="w-full h-8 text-[11px] mt-1 shadow-sm"
                  onClick={() => toast({ title: "Dispatch Requested", description: `Fallback delivery dispatched for ${vil?.name || villageId}.` })}
                >
                  Dispatch via Recommended Modes
                </Button>
              )}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

function hasRecommendedOption(byCommodity) {
  return Object.values(byCommodity).some((r) => r.recommended);
}
