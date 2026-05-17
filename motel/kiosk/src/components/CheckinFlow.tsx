import { useState } from "react";
import { Reservation, api } from "../lib/api";

export default function CheckinFlow({
  reservations,
  refresh,
}: {
  reservations: Reservation[];
  refresh: () => void;
}) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Reservation | null>(null);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  const today = new Date().toISOString().slice(0, 10);
  const arrivals = reservations.filter(
    (r) => r.check_in === today && r.status === "confirmed"
  );
  const filtered = query
    ? arrivals.filter((r) => r.guest_name.toLowerCase().includes(query.toLowerCase()))
    : arrivals;

  async function handleCheckin() {
    if (!selected) return;
    try {
      await api.checkin(selected.id);
      refresh();
      setDone(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Check-in failed");
    }
  }

  if (done && selected) {
    return (
      <div className="max-w-xl mx-auto text-center space-y-4 mt-12">
        <div className="text-5xl">✓</div>
        <h2 className="text-2xl font-bold text-green-400">Checked In!</h2>
        <p className="text-slate-300">{selected.guest_name} — Room {selected.room_id}</p>
        <p className="text-slate-400 text-sm">Check-out: {selected.check_out}</p>
        <button
          onClick={() => { setDone(false); setSelected(null); setQuery(""); }}
          className="mt-4 bg-blue-600 hover:bg-blue-500 px-6 py-2 rounded text-white"
        >
          Another Check-In
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h2 className="text-xl font-semibold">Guest Check-In</h2>
      <input
        type="text"
        placeholder="Search guest name..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="w-full bg-slate-800 border border-slate-600 rounded px-4 py-3 text-lg outline-none focus:border-blue-500"
      />
      <div className="space-y-2">
        {filtered.map((r) => (
          <button
            key={r.id}
            onClick={() => setSelected(r)}
            className={`w-full text-left px-5 py-4 rounded-lg transition-colors ${
              selected?.id === r.id
                ? "bg-blue-700 border-2 border-blue-400"
                : "bg-slate-800 hover:bg-slate-700"
            }`}
          >
            <div className="font-semibold text-lg">{r.guest_name}</div>
            <div className="text-slate-400 text-sm">
              Room {r.room_id} · {r.check_in} → {r.check_out}
              {r.special_requests ? ` · ${r.special_requests}` : ""}
            </div>
          </button>
        ))}
        {filtered.length === 0 && (
          <p className="text-slate-500">
            No arrivals found{query ? ` for "${query}"` : " for today"}.
          </p>
        )}
      </div>
      {error && <p className="text-red-400">{error}</p>}
      {selected && (
        <button
          onClick={() => void handleCheckin()}
          className="w-full bg-green-600 hover:bg-green-500 py-4 rounded-lg text-xl font-bold"
        >
          Check In {selected.guest_name}
        </button>
      )}
    </div>
  );
}
