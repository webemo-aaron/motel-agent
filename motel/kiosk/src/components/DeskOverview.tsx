import { MotelData } from "../hooks/useMotelData";
import { Reservation } from "../lib/api";
import MarvinContext from "./MarvinContext";

function StatusChip({ status }: { status: string }) {
  const colors: Record<string, string> = {
    confirmed: "bg-blue-600",
    checked_in: "bg-green-600",
    checked_out: "bg-slate-500",
    no_show: "bg-red-600",
    cancelled: "bg-slate-700",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded ${colors[status] ?? "bg-slate-600"}`}>
      {status.replace("_", " ")}
    </span>
  );
}

function ReservationRow({ res }: { res: Reservation }) {
  return (
    <div className="flex items-center gap-4 py-2 border-b border-slate-700">
      <span className="w-16 font-mono text-slate-300">Rm {res.room_id}</span>
      <span className="flex-1 font-semibold">{res.guest_name}</span>
      <span className="text-slate-400 text-sm">{res.check_in} → {res.check_out}</span>
      <StatusChip status={res.status} />
    </div>
  );
}

export default function DeskOverview({ data }: { data: MotelData }) {
  const { overview, reservations, loading, error } = data;

  if (loading) return <p className="text-slate-400">Loading...</p>;
  if (error) return <p className="text-red-400">{error}</p>;
  if (!overview) return null;

  const today = new Date().toISOString().slice(0, 10);
  const arrivals = reservations.filter((r) => r.check_in === today);
  const departures = reservations.filter(
    (r) => r.check_out === today && r.status === "checked_in"
  );

  const pct = overview.total_rooms
    ? Math.round((overview.occupied_count / overview.total_rooms) * 100)
    : 0;

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <MarvinContext
        occupancyPct={pct}
        dirtyRooms={overview.dirty_rooms}
        arrivals={overview.arrivals_today}
        unresolvedAlerts={overview.unresolved_alerts}
      />

      <div>
        <div className="flex justify-between text-sm text-slate-400 mb-1">
          <span>Occupancy</span>
          <span>{overview.occupied_count} / {overview.total_rooms} rooms ({pct}%)</span>
        </div>
        <div className="h-4 bg-slate-700 rounded">
          <div
            className="h-4 bg-blue-500 rounded transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4 text-center">
        {[
          { label: "Arrivals Today", value: overview.arrivals_today, color: "text-green-400" },
          { label: "Departures Today", value: overview.departures_today, color: "text-yellow-400" },
          { label: "Rooms Dirty", value: overview.dirty_rooms, color: "text-orange-400" },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-slate-800 rounded-lg p-4">
            <div className={`text-4xl font-bold ${color}`}>{value}</div>
            <div className="text-slate-400 text-sm mt-1">{label}</div>
          </div>
        ))}
      </div>

      <section>
        <h2 className="text-xl font-semibold mb-3 text-green-400">Today's Arrivals</h2>
        {arrivals.length === 0
          ? <p className="text-slate-500">No arrivals today.</p>
          : arrivals.map((r) => <ReservationRow key={r.id} res={r} />)}
      </section>

      <section>
        <h2 className="text-xl font-semibold mb-3 text-yellow-400">Today's Departures</h2>
        {departures.length === 0
          ? <p className="text-slate-500">No pending departures.</p>
          : departures.map((r) => <ReservationRow key={r.id} res={r} />)}
      </section>
    </div>
  );
}
