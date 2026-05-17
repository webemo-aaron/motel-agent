import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";

type KioskTask = "book" | "lookup" | "roominfo" | "help";

function isoDay(offset = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return d.toISOString().slice(0, 10);
}

export default function KioskView({ onAdminUnlock }: { onAdminUnlock: () => void }) {
  const today = useMemo(() => isoDay(0), []);
  const tomorrow = useMemo(() => isoDay(1), []);

  const [task, setTask] = useState<KioskTask>("book");
  const [lastName, setLastName] = useState("");
  const [arrivalDate, setArrivalDate] = useState(today);
  const [phoneLast4, setPhoneLast4] = useState("");

  const [bookName, setBookName] = useState("");
  const [bookPhone, setBookPhone] = useState("");
  const [bookArrival, setBookArrival] = useState(today);
  const [bookDeparture, setBookDeparture] = useState(tomorrow);
  const [bookStayClass, setBookStayClass] = useState<"short"|"medium"|"long">("short");

  const [lookup, setLookup] = useState<any | null>(null);
  const [bookingResult, setBookingResult] = useState<any | null>(null);
  const [roomInfo, setRoomInfo] = useState<any | null>(null);
  const [helpMessage, setHelpMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const IDLE_RESET_SECONDS = 120;
  const [idleRemaining, setIdleRemaining] = useState(IDLE_RESET_SECONDS);

  function resetAll() {
    setLastName("");
    setArrivalDate(today);
    setPhoneLast4("");
    setBookName("");
    setBookPhone("");
    setBookArrival(today);
    setBookDeparture(tomorrow);
    setBookStayClass("short");
    setLookup(null);
    setBookingResult(null);
    setRoomInfo(null);
    setHelpMessage("");
    setTask("book");
  }

  async function doLookup(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const data = await api.kioskLookup({ last_name: lastName, arrival_date: arrivalDate, phone_last4: phoneLast4 || undefined });
      setLookup(data);
      setRoomInfo(null);
      setTask("roominfo");
    } finally { setBusy(false); }
  }

  async function doBook(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const rooms = await api.rooms("available");
      if (!rooms.length) {
        setBookingResult({ error: "No available rooms right now. Please contact operator." });
        return;
      }
      const roomId = String(rooms[0].id);
      const created = await api.kioskBook({
        guest_name: bookName,
        phone: bookPhone,
        check_in: bookArrival,
        check_out: bookDeparture,
        room_id: roomId,
        rate_per_night: 149,
        party_size: 1,
        stay_class: bookStayClass,
      });
      setBookingResult(created);
    } catch (e: any) {
      setBookingResult({ error: e?.message || "Unable to book" });
    } finally { setBusy(false); }
  }

  async function getRoomInfo(reservationId: string) {
    setBusy(true);
    try {
      setRoomInfo(await api.kioskRoomInfo(reservationId));
    } finally { setBusy(false); }
  }

  async function contactOperator() {
    if (!helpMessage.trim()) return;
    setBusy(true);
    try {
      await api.operatorAlert({ message: `[KIOSK HELP] ${helpMessage}`, alert_type: "urgent" });
      setHelpMessage("Sent. Operator notified via Telegram/alert queue.");
    } finally { setBusy(false); }
  }


  useEffect(() => {
    setIdleRemaining(IDLE_RESET_SECONDS);
    const ticker = setInterval(() => {
      setIdleRemaining((s) => {
        if (s <= 1) {
          resetAll();
          return IDLE_RESET_SECONDS;
        }
        return s - 1;
      });
    }, 1000);

    const onActivity = () => setIdleRemaining(IDLE_RESET_SECONDS);
    window.addEventListener("pointerdown", onActivity);
    window.addEventListener("keydown", onActivity);
    window.addEventListener("touchstart", onActivity);

    return () => {
      clearInterval(ticker);
      window.removeEventListener("pointerdown", onActivity);
      window.removeEventListener("keydown", onActivity);
      window.removeEventListener("touchstart", onActivity);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const taskCard = (id: KioskTask, title: string, subtitle: string) => (
    <button
      onClick={() => setTask(id)}
      className={`text-left rounded-xl border p-4 min-h-24 ${task === id ? "bg-indigo-700/40 border-indigo-400" : "bg-slate-800 border-slate-700"}`}
    >
      <div className="text-white font-semibold text-lg">{title}</div>
      <div className="text-slate-300 text-sm mt-1">{subtitle}</div>
    </button>
  );

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <section className="bg-slate-900 border border-slate-700 rounded p-6">
        <h1 className="text-3xl text-white font-bold">Welcome to West Bethel Motel</h1>
        <p className="text-slate-300 mt-2">Fast self-service check-in and booking kiosk</p>
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          <span className="px-2 py-1 rounded bg-slate-800 text-slate-300">Check-in 3:00 PM</span>
          <span className="px-2 py-1 rounded bg-slate-800 text-slate-300">Checkout 11:00 AM</span>
          <span className="px-2 py-1 rounded bg-slate-800 text-slate-300">Quiet Hours 10 PM–8 AM</span>
        </div>
        <p className="text-slate-400 text-sm mt-2">Default arrival is today (check-in starts 3:00 PM). Default departure is tomorrow.</p>
        <p className="text-slate-500 text-xs mt-1">For privacy, this kiosk auto-resets after inactivity. Reset in ~{idleRemaining}s.</p>
      </section>

      <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        {taskCard("book", "Get a Room", "Book tonight or a future stay")}
        {taskCard("lookup", "Find Reservation", "Locate your booking quickly")}
        {taskCard("roominfo", "Get Room Info", "Retrieve room number and code")}
        {taskCard("help", "Contact Operator", "Get live assistance")}
      </section>

      {task === "book" && (
      <section className="bg-slate-900 border border-slate-700 rounded p-6">
        <h2 className="text-xl text-white font-semibold mb-1">Book a Room</h2>
        <div className="text-xs text-slate-400 mb-3">Step 1 of 2: Guest details and dates</div>
        <form onSubmit={doBook} className="grid grid-cols-1 md:grid-cols-6 gap-3">
          <input className="bg-slate-800 rounded px-3 py-4" placeholder="Full name" value={bookName} onChange={e=>setBookName(e.target.value)} required />
          <input className="bg-slate-800 rounded px-3 py-4" placeholder="Phone" value={bookPhone} onChange={e=>setBookPhone(e.target.value)} required />
          <input aria-label="Booking arrival date" className="bg-slate-800 rounded px-3 py-4" type="date" value={bookArrival} onChange={e=>setBookArrival(e.target.value)} required />
          <input aria-label="Departure date" className="bg-slate-800 rounded px-3 py-4" type="date" value={bookDeparture} onChange={e=>setBookDeparture(e.target.value)} required />
          <select aria-label="Stay class" className="bg-slate-800 rounded px-3 py-4" value={bookStayClass} onChange={e=>setBookStayClass(e.target.value as "short"|"medium"|"long")}>
            <option value="short">Short stay</option>
            <option value="medium">Medium stay</option>
            <option value="long">Long stay</option>
          </select>
          <button className="bg-purple-600 rounded px-4 py-4 text-white text-base" disabled={busy}>Book Now</button>
        </form>
        {bookingResult && (
          <div className="mt-3 bg-slate-800 rounded p-3 text-slate-100">
{bookingResult.error ? bookingResult.error : `Booked: ${bookingResult.guest_name} (Room ${bookingResult.room_id}, ${bookingResult.stay_class ?? "short"})`}
          </div>
        )}
      </section>
      )}

      {task === "lookup" && (
      <section className="bg-slate-900 border border-slate-700 rounded p-6">
        <h2 className="text-xl text-white font-semibold mb-1">Find My Reservation</h2>
        <div className="text-xs text-slate-400 mb-3">Step 1 of 2: Enter last name and arrival date</div>
        <form onSubmit={doLookup} className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <input className="bg-slate-800 rounded px-3 py-4" placeholder="Last name" value={lastName} onChange={e=>setLastName(e.target.value)} required />
          <input aria-label="Lookup arrival date" className="bg-slate-800 rounded px-3 py-4" type="date" value={arrivalDate} onChange={e=>setArrivalDate(e.target.value)} required />
          <input className="bg-slate-800 rounded px-3 py-4" placeholder="Phone last 4 (optional)" value={phoneLast4} onChange={e=>setPhoneLast4(e.target.value)} />
          <button className="bg-blue-600 rounded px-4 py-4 text-white" disabled={busy}>Lookup</button>
        </form>
      </section>
      )}

      {task === "roominfo" && (
      <section className="bg-slate-900 border border-slate-700 rounded p-6">
        <h2 className="text-xl text-white font-semibold mb-1">Get Room Info</h2>
        <div className="text-xs text-slate-400 mb-3">Step 2 of 2: Select your reservation</div>
        {lookup ? (
          <div className="mt-2 space-y-2">
            <div className="text-slate-300">Matches: {lookup.count}</div>
            {(lookup.matches || []).map((m: any) => (
              <div key={m.reservation_id} className="bg-slate-800 rounded p-3 flex items-center justify-between">
                <div>{m.guest_name} — Room {m.room_id} — {m.status}</div>
                <button className="bg-emerald-600 rounded px-3 py-2" onClick={()=>getRoomInfo(m.reservation_id)}>Get Room Info</button>
              </div>
            ))}
          </div>
        ) : <div className="text-slate-400">Please use “Find Reservation” first.</div>}

        {roomInfo && (
          <div className="mt-4 bg-slate-800 rounded p-3 text-slate-100">
            <div>Guest: {roomInfo.guest_name}</div>
            <div>Room: {roomInfo.room_id}</div>
            <div>Status: {roomInfo.status}</div>
            <div>Door code: {roomInfo.door_code ?? "Available after check-in"}</div>
            <div className="text-slate-300">{roomInfo.message}</div>
          </div>
        )}
      </section>
      )}

      {task === "help" && (
      <section className="bg-slate-900 border border-slate-700 rounded p-6">
        <h2 className="text-xl text-white font-semibold mb-3">Need Help? Contact Operator</h2>
        <div className="flex gap-3">
          <input className="flex-1 bg-slate-800 rounded px-3 py-4" placeholder="Describe your issue" value={helpMessage} onChange={e=>setHelpMessage(e.target.value)} />
          <button className="bg-amber-600 rounded px-4 py-4" onClick={contactOperator} disabled={busy}>Send Help Request</button>
        </div>
      </section>
      )}

      <section className="flex items-center justify-between">
        <button onClick={resetAll} className="text-sm text-slate-300 underline">Start Over</button>
        <button onClick={onAdminUnlock} className="text-xs text-slate-400 underline">Staff/Admin Access</button>
      </section>
    </div>
  );
}
