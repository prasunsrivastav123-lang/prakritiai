import { useState, useMemo } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import NavRail from "@/components/NavRail";
import PageHeader from "@/components/PageHeader";
import PipelineStatusWidget from "@/components/PipelineStatusWidget";
import VehicleTrackingMap from "@/components/VehicleTrackingMap";
import SimulatedVehicleReporter from "@/components/SimulatedVehicleReporter";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Search, Filter, Truck, User, Package, Clock, MapPin, Navigation, Wifi, WifiOff } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

import useVehicleTracking from "@/hooks/useVehicleTracking";

const GOVERNMENT_ROLES = ["SUPER_ADMIN", "GOVERNMENT_ADMIN", "GOVERNMENT_OFFICER", "DISTRICT_OFFICER"];

export default function VehicleTrackingPage() {
  const { user, ready } = useAuth();
  const { vehicles, activeVehicles, isConnected } = useVehicleTracking();
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [filterStatus, setFilterStatus] = useState("all");

  const filteredVehicles = useMemo(() => {
    return vehicles.filter(v => {
      const matchesSearch = v.gov_id.toLowerCase().includes(search.toLowerCase()) || 
                           v.driver?.toLowerCase().includes(search.toLowerCase());
      const matchesStatus = filterStatus === "all" || v.status === filterStatus;
      return matchesSearch && matchesStatus;
    });
  }, [vehicles, search, filterStatus]);

  const selectedVehicle = useMemo(() => 
    vehicles.find(v => v.gov_id === selectedId), [vehicles, selectedId]
  );

  if (!ready) return null;
  if (!user || !GOVERNMENT_ROLES.includes(user.role)) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="h-screen flex bg-neutral-50 overflow-hidden">
      <NavRail />
      <div className="flex-1 flex flex-col min-w-0">
        <PageHeader 
            title="VEHICLE TRACKING" 
            chip={
                <div className="flex items-center gap-2">
                    {isConnected ? <Wifi size={12} className="text-green-500" /> : <WifiOff size={12} className="text-red-500" />}
                    <span className="text-[10px] uppercase font-bold tracking-widest">{isConnected ? "Connected" : "Reconnecting..."}</span>
                </div>
            } 
        />
        
        <div className="flex-1 flex min-h-0">
          {/* Left Sidebar: Search & List */}
          <div className="w-80 border-r bg-white flex flex-col">
            <div className="p-4 border-b space-y-4">
              <div className="relative">
                <Search className="absolute left-3 top-2.5 h-4 w-4 text-neutral-400" />
                <Input 
                    placeholder="Search Gov ID or Driver..." 
                    className="pl-9 h-9 text-sm"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                />
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" className="flex-1 h-8 text-[11px] gap-2">
                    <Filter size={12} /> Status: All
                </Button>
              </div>
            </div>
            <ScrollArea className="flex-1">
              <div className="p-2 space-y-1">
                {filteredVehicles.map(v => (
                  <div 
                    key={v.gov_id}
                    onClick={() => setSelectedId(v.gov_id)}
                    className={`p-3 rounded-md border cursor-pointer transition-colors ${selectedId === v.gov_id ? 'bg-blue-50 border-blue-200' : 'hover:bg-neutral-50 border-transparent'}`}
                  >
                    <div className="flex justify-between items-start mb-1">
                      <span className="font-bold text-sm text-neutral-900">{v.gov_id}</span>
                      <Badge variant="outline" className="text-[9px] uppercase px-1 h-4">
                        {v.status || "Active"}
                      </Badge>
                    </div>
                    <div className="text-[11px] text-neutral-500 flex items-center gap-1.5">
                        <User size={10} /> {v.driver || "Unknown Driver"}
                    </div>
                    <div className="mt-2 flex justify-between items-center">
                        <div className="text-[10px] font-mono text-neutral-400">{v.type}</div>
                        <div className="text-[10px] font-bold text-blue-600">{Math.round(v.speed || 0)} KM/H</div>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </div>

          {/* Center: Map */}
          <div className="flex-1 relative bg-neutral-100">
             <VehicleTrackingMap 
                vehicles={filteredVehicles} 
                selectedVehicleId={selectedId}
                onVehicleClick={(v) => setSelectedId(v.gov_id)}
             />
             
             <div className="absolute top-4 right-4 z-10">
                <PipelineStatusWidget />
             </div>

             <div className="absolute bottom-4 left-4 z-10">
                <SimulatedVehicleReporter vehicles={activeVehicles} />
             </div>
          </div>

          {/* Right Sidebar: Details */}
          <div className="w-96 border-l bg-white flex flex-col">
            {selectedVehicle ? (
                <ScrollArea className="flex-1">
                    <div className="p-6 space-y-6">
                        <div className="space-y-4">
                            <div className="flex items-center gap-3">
                                <div className="w-12 h-12 rounded-lg bg-blue-100 flex items-center justify-center text-blue-600">
                                    <Truck size={24} />
                                </div>
                                <div>
                                    <h2 className="text-xl font-bold text-neutral-900">{selectedVehicle.gov_id}</h2>
                                    <p className="text-xs text-neutral-500 uppercase tracking-wider font-semibold">{selectedVehicle.type}</p>
                                </div>
                            </div>

                            <div className="grid grid-cols-2 gap-3">
                                <Card className="shadow-none border-neutral-100 bg-neutral-50/50">
                                    <CardContent className="p-3">
                                        <div className="text-[10px] text-neutral-400 uppercase font-bold">Speed</div>
                                        <div className="text-lg font-black text-neutral-900">{Math.round(selectedVehicle.speed || 0)} <span className="text-[10px] font-normal text-neutral-400">km/h</span></div>
                                    </CardContent>
                                </Card>
                                <Card className="shadow-none border-neutral-100 bg-neutral-50/50">
                                    <CardContent className="p-3">
                                        <div className="text-[10px] text-neutral-400 uppercase font-bold">ETA</div>
                                        <div className="text-lg font-black text-blue-600">{selectedVehicle.eta || "24m"}</div>
                                    </CardContent>
                                </Card>
                            </div>
                        </div>

                        <div className="space-y-3">
                            <h3 className="text-[11px] font-bold uppercase text-neutral-400 tracking-widest border-b pb-1">Current Status</h3>
                            <div className="space-y-2.5">
                                <div className="flex items-center gap-3 text-sm">
                                    <MapPin size={16} className="text-neutral-400" />
                                    <span className="text-neutral-700 font-medium">Lat: {selectedVehicle.lat?.toFixed(4)}, Lon: {selectedVehicle.lon?.toFixed(4)}</span>
                                </div>
                                <div className="flex items-center gap-3 text-sm">
                                    <Navigation size={16} className="text-neutral-400" />
                                    <span className="text-neutral-700 font-medium">Heading: {Math.round(selectedVehicle.heading || 0)}°</span>
                                </div>
                                <div className="flex items-center gap-3 text-sm">
                                    <Package size={16} className="text-neutral-400" />
                                    <span className="text-neutral-700 font-medium">Cargo: {selectedVehicle.cargo_load || "Standard Supply"}</span>
                                </div>
                            </div>
                        </div>

                        <div className="space-y-3">
                            <h3 className="text-[11px] font-bold uppercase text-neutral-400 tracking-widest border-b pb-1">Cargo Table</h3>
                            <div className="border rounded-md">
                                <Table>
                                    <TableHeader>
                                        <TableRow className="bg-neutral-50 hover:bg-neutral-50">
                                            <TableHead className="h-8 text-[10px] font-bold uppercase">Item</TableHead>
                                            <TableHead className="h-8 text-[10px] font-bold uppercase text-right">Qty</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {(selectedVehicle.cargo || [{item: "Medical Kits", qty: 450}, {item: "Drinking Water", qty: 1200}]).map((item, i) => (
                                            <TableRow key={i} className="h-8 hover:bg-transparent">
                                                <TableCell className="py-1.5 text-[11px] font-medium">{item.item}</TableCell>
                                                <TableCell className="py-1.5 text-[11px] text-right font-mono">{item.qty}</TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            </div>
                        </div>

                        <div className="pt-4 flex gap-2">
                            <Button size="sm" className="flex-1 bg-blue-600 hover:bg-blue-700 h-9">Update Status</Button>
                            <Button size="sm" variant="outline" className="flex-1 h-9 text-red-500 border-red-100 hover:bg-red-50">Recall</Button>
                        </div>
                    </div>
                </ScrollArea>
            ) : (
                <div className="flex-1 flex flex-col items-center justify-center text-neutral-400 p-8 text-center gap-3">
                    <Truck size={48} className="opacity-10" />
                    <p className="text-sm">Select a vehicle from the list to view real-time telemetry and cargo details.</p>
                </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
