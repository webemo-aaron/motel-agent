import { useState } from "react";
import { Room, api } from "../lib/api";

const STATUS_COLORS: Record<string, string> = {
  available: "bg-green-700 hover:bg-green-600",
  occupied: "bg-blue-700 hover:bg-blue-600",
  dirty: "bg-orange-700 hover:bg-orange-600",
  maintenance: "bg-red-800 hover:bg-red-700",
};

const STATUS_LABELS: Record<string, string> = {
  available: "Available",
  occupied: "Occupied",
  dirty: "Needs Cleaning",
  maintenance: "Maintenance",
};

function RoomCard({ room, onStatusChange }: { room: Room; onStatusChange: () => void }) {
  const [updating, setUpdating] = useState(false);

  async function markClean() {
    setUpdating(true);
    await api.updateRoomStatus(room.id, "available", "Cleaned");
    onStatusChange();
    setUpdating(false);
  }

  return (
    <div className={`rounded-xl p-5 transition-colors ${STATUS_COLORS[room.status] ?? "bg-slate-700"}`}>
      <div className="text-2xl font-bold">Rm {room.id}</div>
      <div className="text-sm mt-1 opacity-80">{STATUS_LABELS[room.status] ?? room.status}</div>
      {room.notes && <div className="text-xs mt-1 opacity-60">{room.notes}</div>}
      {room.status === "dirty" && (
        <button
          onClick={() => void markClean()}
          disabled={updating}
          className="mt-3 text-xs bg-white/20 hover:bg-white/30 px-3 py-1 rounded"
        >
          {updating ? "Updating..." : "Mark Clean"}
        </button>
      )}
    </div>
  );
}

export default function RoomGrid({ rooms, refresh }: { rooms: Room[]; refresh: () => void }) {
  if (rooms.length === 0)
    return <p className="text-slate-400">No rooms in database. Add rooms via the agent.</p>;

  return (
    <div>
      <h2 className="text-xl font-semibold mb-4">Room Status</h2>
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-4">
        {rooms.map((room) => (
          <RoomCard key={room.id} room={room} onStatusChange={refresh} />
        ))}
      </div>
      <div className="flex gap-6 mt-6 text-sm">
        {Object.entries(STATUS_LABELS).map(([k, v]) => (
          <span key={k} className="flex items-center gap-2">
            <span className={`w-3 h-3 rounded-sm inline-block ${STATUS_COLORS[k]?.split(" ")[0] ?? ""}`} />
            {v}
          </span>
        ))}
      </div>
    </div>
  );
}
