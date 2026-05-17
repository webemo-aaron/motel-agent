import { Routes, Route, Navigate, NavLink, useLocation } from "react-router-dom";
import { useMotelData } from "./hooks/useMotelData";
import DeskOverview from "./components/DeskOverview";
import RoomGrid from "./components/RoomGrid";
import CheckinFlow from "./components/CheckinFlow";
import CheckoutFlow from "./components/CheckoutFlow";
import AlertBanner from "./components/AlertBanner";
import AgentChat from "./components/AgentChat";
import ManagerPortal from "./components/ManagerPortal";
import RateIntelligence from "./components/RateIntelligence";
import { VoiceSettings } from "./components/VoiceSettings";
import { api } from "./lib/api";
import { useEffect, useMemo, useState } from "react";
import KioskView from "./components/KioskView";

function AdminUnlock({ onUnlocked }: { onUnlocked: (token: string) => void }) {
  const [pin, setPin] = useState("");
  const [err, setErr] = useState("");
  async function submit() {
    try {
      const res = await api.adminUnlock(pin);
      onUnlocked(res.token);
    } catch {
      setErr("Invalid PIN");
    }
  }
  return (
    <div className="max-w-md mx-auto bg-slate-900 border border-slate-700 rounded p-6 mt-10">
      <h2 className="text-xl font-semibold text-white">Administrator Unlock</h2>
      <input className="mt-4 w-full bg-slate-800 rounded px-3 py-3" type="password" value={pin} onChange={e=>setPin(e.target.value)} placeholder="Enter PIN" />
      {err && <div className="text-red-400 mt-2">{err}</div>}
      <button className="mt-4 bg-blue-600 rounded px-4 py-3" onClick={submit}>Unlock</button>
    </div>
  );
}

function AppShell({ qaFailCount, chatOpen, setChatOpen, data, onExitAdmin }: any) {
  const location = useLocation();
  const [navOpen, setNavOpen] = useState<{ frontDesk: boolean; management: boolean }>({ frontDesk: true, management: true });

  useEffect(() => {
    try {
      const raw = localStorage.getItem('motel_admin_nav_state');
      if (raw) {
        const parsed = JSON.parse(raw);
        setNavOpen({
          frontDesk: parsed.frontDesk !== false,
          management: parsed.management !== false,
        });
      }
    } catch {}
  }, []);

  useEffect(() => {
    localStorage.setItem('motel_admin_nav_state', JSON.stringify(navOpen));
  }, [navOpen]);

  const toggleNav = (key: 'frontDesk' | 'management') => {
    setNavOpen((s) => ({ ...s, [key]: !s[key] }));
  };
  const topModules = [
    { to: '/desk', label: 'Operations' },
    { to: '/manager', label: 'Manager' },
    { to: '/rates', label: 'Revenue and Rates' },
    { to: '/settings', label: 'Settings' },
  ];

  const topClass = ({ isActive }: { isActive: boolean }) =>
    isActive ? 'bg-indigo-600 text-white px-3 py-1.5 rounded text-sm font-semibold' : 'bg-slate-800 text-slate-300 hover:text-white px-3 py-1.5 rounded text-sm';
  const sideClass = ({ isActive }: { isActive: boolean }) =>
    isActive ? 'text-white font-semibold bg-slate-800 rounded px-2 py-1' : 'text-slate-300 hover:text-white px-2 py-1';

  const sectionTitle = useMemo(() => {
    if (location.pathname.startsWith('/manager')) return 'Manager Growth and Events';
    if (location.pathname.startsWith('/rates')) return 'Rate Intelligence';
    if (location.pathname.startsWith('/settings')) return 'Platform Settings';
    return 'Front Desk Operations';
  }, [location.pathname]);

  return (
    <div className="min-h-screen flex flex-col bg-slate-950 text-slate-100">
      {data.overview && data.overview.unresolved_alerts > 0 && (
        <AlertBanner count={data.overview.unresolved_alerts} />
      )}

      <header data-testid="admin-topbar" className="border-b border-slate-800 bg-slate-900 px-4 py-3">
        <div className="flex items-center gap-4">
          <div>
            <div className="text-white font-bold">West Bethel Motel Admin</div>
            <div className="text-xs text-slate-400">Unified operations, guest support, revenue control</div>
          </div>
          <div className="flex gap-2 ml-6">
            {topModules.map((m: any) => (
              <NavLink key={m.to} to={m.to} className={topClass}>{m.label}</NavLink>
            ))}
          </div>
          <span className="flex-1" />
          <div className="text-xs text-slate-400">{data.overview ? `${data.overview.occupied_count}/${data.overview.total_rooms} occupied` : '...'}</div>
          <button onClick={() => setChatOpen((v: boolean) => !v)} className="bg-blue-600 hover:bg-blue-500 px-3 py-2 rounded text-white text-sm">
            {chatOpen ? 'Close Chat' : 'Ask Agent'}
          </button>
        </div>
      </header>

      <div className="flex flex-1">
        <aside data-testid="admin-sidebar" className="w-72 shrink-0 border-r border-slate-800 bg-slate-900 p-4">
          <h2 className="text-white text-lg font-semibold">Admin Navigation</h2>
          <p className="text-xs text-slate-400 mt-1">{sectionTitle}</p>

          <div className="mt-4" data-testid="nav-group-frontdesk">
            <button type="button" onClick={() => toggleNav('frontDesk')} className="w-full flex items-center justify-between text-[11px] uppercase tracking-wide text-slate-500 mb-1">
              <span>Front Desk</span><span>{navOpen.frontDesk ? '−' : '+'}</span>
            </button>
            {navOpen.frontDesk && (
              <nav className="flex flex-col gap-1 text-sm" data-testid="nav-frontdesk-links">
                <NavLink to="/desk" className={sideClass}>Desk Overview</NavLink>
                <NavLink to="/rooms" className={sideClass}>Room Inventory</NavLink>
                <NavLink to="/checkin" className={sideClass}>Check In Flow</NavLink>
                <NavLink to="/checkout" className={sideClass}>Check Out Flow</NavLink>
              </nav>
            )}
          </div>

          <div className="mt-4" data-testid="nav-group-management">
            <button type="button" onClick={() => toggleNav('management')} className="w-full flex items-center justify-between text-[11px] uppercase tracking-wide text-slate-500 mb-1">
              <span>Management</span><span>{navOpen.management ? '−' : '+'}</span>
            </button>
            {navOpen.management && (
              <nav className="flex flex-col gap-1 text-sm" data-testid="nav-management-links">
                <NavLink to="/manager" className={sideClass}>Manager Portal</NavLink>
                <a href="/manager#campaigns" className="text-slate-400 hover:text-white pl-4 text-xs">Advertising and Campaigns</a>
                <a href="/manager#events" className="text-slate-400 hover:text-white pl-4 text-xs">Events</a>
                <a href="/manager#groups" className="text-slate-400 hover:text-white pl-4 text-xs">Groups and Leads</a>
                <NavLink to="/rates" className={sideClass}>Rate Intelligence {qaFailCount > 0 ? <span className="ml-1 inline-block bg-red-600 text-white text-[10px] px-1.5 py-0.5 rounded-full">{qaFailCount}</span> : null}</NavLink>
                <NavLink to="/settings" className={sideClass}>Settings</NavLink>
              </nav>
            )}
          </div>

          <div className="mt-6 space-y-2">
            <button className="w-full text-xs underline text-slate-300" onClick={onExitAdmin}>Exit Admin</button>
          </div>
        </aside>

        <main className="flex-1 p-6">
          <Routes>
            <Route path="/desk" element={<DeskOverview data={data} />} />
            <Route path="/rooms" element={<RoomGrid rooms={data.rooms} refresh={data.refresh} />} />
            <Route path="/checkin" element={<CheckinFlow reservations={data.reservations} refresh={data.refresh} />} />
            <Route path="/checkout" element={<CheckoutFlow reservations={data.reservations} refresh={data.refresh} />} />
            <Route path="/manager" element={<ManagerPortal stats={data.stats} />} />
            <Route path="/rates" element={<RateIntelligence />} />
            <Route path="/settings" element={<VoiceSettings />} />
            <Route path="*" element={<Navigate to="/desk" replace />} />
          </Routes>
        </main>
      </div>

      {chatOpen && <AgentChat onClose={() => setChatOpen(false)} />}
    </div>
  );
}

export default function App() {
  const data = useMotelData(30_000);
  const [chatOpen, setChatOpen] = useState(false);
  const [qaFailCount, setQaFailCount] = useState(0);
  const [adminUnlocked, setAdminUnlocked] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);
  const [unlockMode, setUnlockMode] = useState(false);

  useEffect(() => {
    let alive = true;
    const boot = async () => {
      const token = localStorage.getItem('motel_admin_token') || '';
      if (!token) {
        if (alive) setAuthChecked(true);
        return;
      }
      try {
        const v = await api.adminValidate(token);
        if (alive) setAdminUnlocked(!!v.valid);
      } catch {
        if (alive) setAdminUnlocked(false);
      } finally {
        if (alive) setAuthChecked(true);
      }
    };
    void boot();
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const q = await api.qaSummary(24);
        if (alive) setQaFailCount(q.fail_count ?? 0);
      } catch {}
    };
    void load();
    const t = setInterval(load, 60_000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  if (!authChecked) {
    return <div className="min-h-screen bg-slate-950 text-slate-300 p-6">Loading kiosk...</div>;
  }

  if (!adminUnlocked) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 p-6">
        {unlockMode ? <AdminUnlock onUnlocked={(token) => { localStorage.setItem("motel_admin_token", token); setAdminUnlocked(true); }} /> : <KioskView onAdminUnlock={() => setUnlockMode(true)} />}
      </div>
    );
  }

  return (
    <AppShell
      qaFailCount={qaFailCount}
      chatOpen={chatOpen}
      setChatOpen={setChatOpen}
      data={data}
      onExitAdmin={() => { localStorage.removeItem("motel_admin_token"); setAdminUnlocked(false); setUnlockMode(false); }}
    />
  );
}
