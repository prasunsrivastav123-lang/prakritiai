import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Building2, LayoutDashboard, Map as MapIcon, Truck, TriangleAlert, Package, Bell, Radar, Radio, User as UserIcon, ScrollText, Route as RouteIcon, Boxes, LogOut, Menu, X } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

const NAV_GROUPS = {
  gov: [
    { to: "/command-center", icon: LayoutDashboard, label: "Command" },
    { to: "/map", icon: MapIcon, label: "GIS Pipeline" },
    { to: "/routes", icon: RouteIcon, label: "Routes" },
    { to: "/vehicle-tracking", icon: Truck, label: "Tracking" },
    { to: "/vehicles", icon: Boxes, label: "Fleet" },
    { to: "/incidents", icon: TriangleAlert, label: "Incidents" },
    { to: "/supply", icon: Boxes, label: "Supply" },
    { to: "/predictions", icon: Radar, label: "Predictions" },
    { to: "/alerts", icon: Bell, label: "Alerts" },
    { to: "/audit", icon: ScrollText, label: "Audit" },
  ],
  logistics: [
    { to: "/logistics", icon: Package, label: "Workspace" },
    { to: "/vehicles", icon: Truck, label: "Fleet" },
    { to: "/routes", icon: RouteIcon, label: "Routes" },
    { to: "/alerts", icon: Bell, label: "Alerts" },
  ],
  field: [
    { to: "/field", icon: Radio, label: "Report" },
    { to: "/vehicles", icon: Truck, label: "Fleet" },
    { to: "/routes", icon: RouteIcon, label: "Road Status" },
    { to: "/alerts", icon: Bell, label: "Alerts" },
  ],
  public: [
    { to: "/public", icon: UserIcon, label: "Advisories" },
    { to: "/routes", icon: RouteIcon, label: "Road Status" },
    { to: "/alerts", icon: Bell, label: "Alerts" },
  ],
};

function groupFor(role) {
  if (["SUPER_ADMIN", "GOVERNMENT_ADMIN", "GOVERNMENT_OFFICER", "DISTRICT_OFFICER"].includes(role)) return "gov";
  if (["LOGISTICS_OPERATOR", "DRIVER"].includes(role)) return "logistics";
  if (role === "FIELD_OFFICER") return "field";
  return "public";
}

export default function NavRail() {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  if (!user || typeof user !== "object") return null;
  const items = NAV_GROUPS[groupFor(user.role)] || [];
  const currentItem = items.find((it) => pathname === it.to || pathname.startsWith(it.to + "/"));

  return (
    <>
      {/* Mobile Top Header */}
      <div className="md:hidden w-full bg-white border-b hairline px-4 py-2.5 flex items-center justify-between flex-shrink-0 z-30">
        <div className="flex items-center gap-2.5">
          <Link
            to="/"
            className="w-8 h-8 rounded-sm bg-[var(--accent-primary)] flex items-center justify-center text-white"
            title="NERIS home"
            data-testid="mobile-nav-home"
          >
            <Building2 size={16} />
          </Link>
          <div className="leading-none">
            <div className="text-[13px] font-semibold tracking-tight">NERIS</div>
            {currentItem && (
              <span className="text-[10px] text-neutral-500 font-medium">{currentItem.label}</span>
            )}
          </div>
        </div>
        
        <button
          onClick={() => setMobileOpen(true)}
          className="p-1.5 rounded-md border hairline text-neutral-700 hover:bg-[var(--surface-sunken)] transition-colors flex items-center justify-center"
          aria-label="Open menu"
          data-testid="mobile-hamburger-btn"
        >
          <Menu size={20} />
        </button>
      </div>

      {/* Mobile Drawer Overlay */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex">
          <div
            className="fixed inset-0 bg-black/40 backdrop-blur-xs transition-opacity"
            onClick={() => setMobileOpen(false)}
            data-testid="mobile-menu-backdrop"
          />
          
          <div className="relative w-72 max-w-[82vw] bg-white h-full flex flex-col shadow-2xl z-50 p-4">
            <div className="flex items-center justify-between pb-3 mb-2 border-b hairline">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-sm bg-[var(--accent-primary)] flex items-center justify-center text-white">
                  <Building2 size={16} />
                </div>
                <div>
                  <div className="text-[13px] font-semibold tracking-tight">NERIS</div>
                  <div className="text-[10px] font-mono text-neutral-500 uppercase">{user.role?.replace(/_/g, " ")}</div>
                </div>
              </div>
              <button
                onClick={() => setMobileOpen(false)}
                className="p-1.5 rounded-md text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100"
                aria-label="Close menu"
                data-testid="mobile-menu-close"
              >
                <X size={18} />
              </button>
            </div>

            <nav className="flex-1 overflow-y-auto space-y-1 py-2">
              {items.map((it) => {
                const active = pathname === it.to || pathname.startsWith(it.to + "/");
                return (
                  <Link
                    key={it.to}
                    to={it.to}
                    onClick={() => setMobileOpen(false)}
                    data-testid={`mobile-nav-${it.label.toLowerCase().replace(/\s+/g, "-")}`}
                    className={`flex items-center gap-3 px-3 py-2.5 rounded-md text-[13px] font-medium transition-colors ${
                      active
                        ? "bg-[var(--accent-soft)] text-[var(--accent-primary)] font-semibold"
                        : "text-neutral-600 hover:text-[var(--text-primary)] hover:bg-[var(--surface-sunken)]"
                    }`}
                  >
                    <it.icon size={18} strokeWidth={1.75} />
                    {it.label}
                  </Link>
                );
              })}
            </nav>

            <div className="pt-3 border-t hairline flex items-center justify-between">
              <div className="flex items-center gap-2.5 min-w-0">
                <div
                  className="w-8 h-8 rounded-full bg-[var(--accent-primary)] text-white flex items-center justify-center text-[12px] font-semibold flex-shrink-0"
                  title={`${user.name} · ${user.role}`}
                >
                  {(user.name || "U").slice(0, 1).toUpperCase()}
                </div>
                <div className="min-w-0">
                  <div className="text-[12px] font-medium truncate text-neutral-800">{user.name}</div>
                  <div className="text-[10px] text-neutral-400 truncate">{user.email}</div>
                </div>
              </div>
              <button
                onClick={() => {
                  setMobileOpen(false);
                  logout();
                }}
                title="Sign out"
                data-testid="mobile-nav-logout-button"
                className="p-2 rounded-md text-neutral-500 hover:text-red-700 hover:bg-red-50 flex items-center justify-center flex-shrink-0"
              >
                <LogOut size={16} />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Desktop Vertical NavRail */}
      <nav
        data-testid="nav-rail"
        className="hidden md:flex w-16 flex-shrink-0 bg-white border-r hairline flex-col items-center py-3 gap-1 z-30"
        aria-label="Primary"
      >
        <Link
          to="/"
          className="w-9 h-9 rounded-sm bg-[var(--accent-primary)] flex items-center justify-center text-white mb-3"
          title="NERIS home"
          data-testid="nav-home"
        >
          <Building2 size={17} />
        </Link>

        {items.map((it) => {
          const active = pathname === it.to || pathname.startsWith(it.to + "/");
          return (
            <Link
              key={it.to}
              to={it.to}
              title={it.label}
              data-testid={`nav-${it.label.toLowerCase().replace(/\s+/g, "-")}`}
              className={`w-12 py-2 rounded-md flex flex-col items-center gap-0.5 text-[9.5px] font-medium tracking-wide transition-colors ${
                active
                  ? "bg-[var(--accent-soft)] text-[var(--accent-primary)]"
                  : "text-neutral-500 hover:text-[var(--text-primary)] hover:bg-[var(--surface-sunken)]"
              }`}
              aria-current={active ? "page" : undefined}
            >
              <it.icon size={17} strokeWidth={1.75} />
              {it.label}
            </Link>
          );
        })}

        <div className="flex-1" />

        <div
          className="w-8 h-8 rounded-full bg-[var(--accent-primary)] text-white flex items-center justify-center text-[11px] font-semibold"
          title={`${user.name} · ${user.role}`}
          data-testid="nav-user-avatar"
        >
          {(user.name || "U").slice(0, 1).toUpperCase()}
        </div>
        <button
          onClick={logout}
          title="Sign out"
          data-testid="nav-logout-button"
          className="mt-1 w-10 py-1.5 rounded-md text-neutral-500 hover:text-[var(--status-blocked)] hover:bg-red-50 flex items-center justify-center"
        >
          <LogOut size={15} />
        </button>
      </nav>
    </>
  );
}

