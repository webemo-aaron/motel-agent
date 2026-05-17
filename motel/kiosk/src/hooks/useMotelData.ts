import { useState, useEffect, useCallback } from "react";
import { api, Overview, Room, Reservation, Stats } from "../lib/api";

export interface MotelData {
  overview: Overview | null;
  rooms: Room[];
  reservations: Reservation[];
  stats: Stats | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useMotelData(intervalMs = 30_000): MotelData {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [ov, rm, res, st] = await Promise.all([
        api.overview(),
        api.rooms(),
        api.reservations(),
        api.stats(),
      ]);
      setOverview(ov);
      setRooms(rm);
      setReservations(res);
      setStats(st);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load motel data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = setInterval(() => void refresh(), intervalMs);
    return () => clearInterval(id);
  }, [refresh, intervalMs]);

  return { overview, rooms, reservations, stats, loading, error, refresh };
}
