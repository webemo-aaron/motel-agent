import { useState } from "react";
import { Reservation, api } from "../lib/api";

export default function CheckoutFlow({
  reservations,
  refresh,
}: {
  reservations: Reservation[];
  refresh: () => void;
}) {
  const [selected, setSelected] = useState<Reservation | null>(null);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  const today = new Date().toISOString().slice(0, 10);
  const departures = reservations.filter(
    (r) => r.check_out === today && r.status === "checked_in"
  );

  async function handleCheckout() {
    if (!selected) return;
    try {
      await api.checkout(selected.id);
      refresh();
      setDone(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Check-out failed");
    }
  }

  if (done && selected) {
    return (
      <div className="max-w-xl mx-auto text-center space-y-4 mt-12">
        <div className="text-5xl">✓</div>
        <h2 className="text-2xl font-bold text-yellow-400">Checked Out!</h2>
        <p className="text-slate-300">{selected.guest_name} — Room {selected.room_id}</p>
        <p className="text-slate-400 text-sm">Room has been queued for housekeeping.</p>
        <button
          onClick={() => { setDone(false); setSelected(null); }}
          className="mt-4 bg-blue-600 hover:bg-blue-500 px-6 py-2 rounded text-white"
        >
          Another Check-Out
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h2 className="text-xl font-semibold">Guest Check-Out</h2>
      <div className="space-y-2">
        {departures.map((r) => (
          <button
            key={r.id}
            onClick={() => setSelected(r)}
            className={`w-full text-left px-5 py-4 rounded-lg transition-colors ${
              selected?.id === r.id
                ? "bg-yellow-700 border-2 border-yellow-400"
                : "bg-slate-800 hover:bg-slate-700"
            }`}
          >
            <div className="font-semibold text-lg">{r.guest_name}</div>
            <div className="text-slate-400 text-sm">
              Room {r.room_id} · checked in {r.check_in}
            </div>
          </button>
        ))}
        {departures.length === 0 && (
          <p className="text-slate-500">
            No guests currently checked in with today's check-out.
          </p>
        )}
      </div>
      {error && <p className="text-red-400">{error}</p>}
      {selected && (
        <button
          onClick={() => void handleCheckout()}
          className="w-full bg-yellow-600 hover:bg-yellow-500 py-4 rounded-lg text-xl font-bold"
        >
          Check Out {selected.guest_name}
        </button>
      )}
    </div>
  );
}
