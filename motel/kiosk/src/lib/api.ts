const MOTEL_API = "/api/motel";

export interface Overview {
  date: string;
  total_rooms: number;
  occupied_count: number;
  dirty_rooms: number;
  arrivals_today: number;
  departures_today: number;
  unresolved_alerts: number;
}

export interface Room {
  id: string;
  name: string | null;
  floor: number;
  type: string;
  max_occupancy: number;
  status: "available" | "occupied" | "dirty" | "maintenance";
  current_code: string | null;
  notes: string | null;
}

export interface Reservation {
  id: string;
  guest_name: string;
  room_id: string;
  check_in: string;
  check_out: string;
  status: string;
  party_size: number;
  door_code: string | null;
  special_requests: string | null;
  email: string | null;
  phone: string | null;
}

export interface Stats extends Overview {
  occupancy_pct: number;
  revenue_today: number;
}

async function get<T>(path: string): Promise<T> {
  const resp = await fetch(`${MOTEL_API}${path}`);
  if (!resp.ok) throw new Error(`API error ${resp.status}: ${path}`);
  return resp.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(`${MOTEL_API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`API error ${resp.status}: ${path}`);
  return resp.json() as Promise<T>;
}

export interface MarvinInsight {
  type: "alert" | "recommendation" | "priority";
  priority: "critical" | "high" | "medium" | "low";
  message: string;
  context?: Record<string, unknown>;
}

export interface MarvinContextResponse {
  insights: MarvinInsight[];
  overview: Overview;
  timestamp: string;
}


export interface ManagerPackage {
  name: string;
  segment: string;
  pricing_hint: string;
}



export interface CampaignPlan {
  id: string;
  week: string;
  channel: string;
  objective: string;
  offer: string;
  budget: number;
  owner: string;
  status: string;
  created_at: string;
}

export interface EventPlan {
  id: string;
  date: string;
  title: string;
  event_type: string;
  expected_guests: number;
  room_block: number;
  notes: string;
  status: string;
}

export interface LeadPlan {
  id: string;
  name: string;
  segment: string;
  contact: string;
  source: string;
  est_value: number;
  stage: string;
  notes: string;
  updated_at: string;
}

export interface EBikeSettings {
  fleet_size: number;
  half_day_rate: number;
  full_day_rate: number;
}

export interface EBikeBooking {
  id: string;
  guest_name: string;
  date: string;
  duration: string;
  bikes: number;
  status: string;
}

export interface ManagerRecommendations {
  recommendations: Array<{ priority: string; item: string }>;
  funnel: { new: number; qualified: number; proposal: number; won: number; lost: number };
}

export interface RateAlertItem extends Record<string, unknown> {
  id: string;
  acknowledged: boolean;
}

export interface CompetitorCard {
  property: string;
  count: number;
  median_rate: number | null;
  min_rate: number | null;
  markets: string[];
  last_seen: string;
  sources: string[];
  confidence: "high" | "medium" | "low";
}

export interface RateSummary {
  health: Record<string, unknown>;
  snapshot_count: number;
  alerts_count: number;
  sample_snapshot: Array<Record<string, unknown>>;
  sample_alerts: Array<Record<string, unknown>>;
}

export interface ManagerAutomationSettings {
  auto_recovery_enabled: boolean;
  recovery_threshold_pct: number;
  auto_briefing_alert_enabled: boolean;
}

export interface WeeklyBriefing {
  briefing: string;
  actions: string[];
}

export interface ManagerPlan {
  campaigns: CampaignPlan[];
  events: EventPlan[];
  leads: LeadPlan[];
  ebike: { settings: EBikeSettings; bookings: EBikeBooking[] };
}

export interface ManagerStrategy {
  timestamp: string;
  strategy_phase: string;
  occupancy_pct: number;
  revenue_today: number;
  strategic_focus: string[];
  operational_risks: string[];
  packages: ManagerPackage[];
  event_products: string[];
  integration_endpoints: Record<string, string>;
  work_orders: Record<string, unknown>;
}

export const api = {
  overview: () => get<Overview>("/overview"),
  stats: () => get<Stats>("/stats"),
  rooms: (status?: string) =>
    get<Room[]>(status ? `/rooms?status=${status}` : "/rooms"),
  reservations: (forDate?: string, status?: string) => {
    const params = new URLSearchParams();
    if (forDate) params.set("for_date", forDate);
    if (status) params.set("status", status);
    const qs = params.toString();
    return get<Reservation[]>(`/reservations${qs ? `?${qs}` : ""}`);
  },
  marvinContext: () => get<MarvinContextResponse>("/marvin-context"),
  managerStrategy: () => get<ManagerStrategy>("/manager/strategy"),
  managerPlan: () => get<ManagerPlan>("/manager/plan"),
  createCampaign: (body: Omit<CampaignPlan, "id" | "created_at">) => post<CampaignPlan>("/manager/campaigns", body),
  createEvent: (body: Omit<EventPlan, "id">) => post<EventPlan>("/manager/events", body),
  createLead: (body: Omit<LeadPlan, "id" | "updated_at">) => post<LeadPlan>("/manager/leads", body),
  updateLead: (lead_id: string, body: { stage?: string; notes?: string }) =>
    fetch(`${MOTEL_API}/manager/leads/${lead_id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then((r) => r.json()),
  leadHistory: (lead_id: string) => get<{ lead_id: string; history: Array<{ date: string; stage: string; notes: string }> }>(`/manager/leads/${lead_id}/history`),
  setEbikeSettings: (body: EBikeSettings) => post<EBikeSettings>("/manager/ebike/settings", body),
  createEbikeBooking: (body: Omit<EBikeBooking, "id">) => post<EBikeBooking>("/manager/ebike/bookings", body),
  weeklyBriefing: () => get<WeeklyBriefing>("/manager/weekly-briefing"),
  sendWeeklyBriefing: () => post<{ id: string }>("/manager/send-weekly-briefing", {}),
  managerRecommendations: () => get<ManagerRecommendations>("/manager/recommendations"),
  updateEbikeBooking: (booking_id: string, body: Omit<EBikeBooking, "id">) =>
    fetch(`${MOTEL_API}/manager/ebike/bookings/${booking_id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then((r) => r.json()),
  deleteEbikeBooking: (booking_id: string) => fetch(`${MOTEL_API}/manager/ebike/bookings/${booking_id}`, { method: "DELETE" }).then((r) => r.json()),
  managerWeeklyExport: () => get<{ snapshot_date: string } & Record<string, unknown>>("/manager/export/weekly"),
  triggerRecoverySprint: () => post<{ triggered: boolean; occupancy_pct: number }>("/manager/recovery-sprint", {}),
  automationSettings: () => get<ManagerAutomationSettings>("/manager/automation/settings"),
  saveAutomationSettings: (body: ManagerAutomationSettings) => post<ManagerAutomationSettings>("/manager/automation/settings", body),
  runAutomationDaily: () => post<{ date: string; actions: Array<{ type: string }> }>("/manager/automation/run-daily", {}),
  automationLogs: () => get<{ logs: Array<{ date: string; occupancy_pct: number; actions: Array<{ type: string }> }> }>("/manager/automation/logs"),
  ratesHealth: () => get<Record<string, unknown>>("/rates/health"),
  ratesSnapshot: (limit = 200) => get<{ generated_at: string; count: number; items: Array<Record<string, unknown>> }>(`/rates/snapshot?limit=${limit}`),
  ratesAlerts: (limit = 200) => get<{ generated_at: string; count: number; items: RateAlertItem[] }>(`/rates/alerts?limit=${limit}`),
  ratesCalendar: () => get<{ from: string | null; to: string | null; days: string[]; local_events: Array<Record<string, unknown>> }>("/rates/calendar"),
  ratesCompetitors: (days = 30, market = "all") => get<{ generated_at: string; days: number; market: string; count: number; items: CompetitorCard[] }>(`/rates/competitors?days=${days}&market=${encodeURIComponent(market)}`),
  acknowledgeRateAlert: (alert_id: string) => post<{ acknowledged: string }>("/rates/alerts/ack", { alert_id }),
  ratesSummary: () => get<RateSummary>("/rates/summary"),
  qaSummary: (hours = 24) => get<QaSummary>(`/manager/qa-summary?hours=${hours}`),
  kioskConfig: () => get<any>("/kiosk/config"),
  kioskLookup: (payload: { last_name: string; arrival_date: string; phone_last4?: string }) => post<{ count: number; matches: KioskLookupMatch[] }>("/kiosk/lookup", payload),
  kioskRoomInfo: (reservation_id: string) => post<any>("/kiosk/room-info", { reservation_id }),
  kioskBook: (payload: { guest_name: string; check_in: string; check_out: string; room_id: string; rate_per_night?: number; email?: string; phone?: string; party_size?: number; stay_class?: "short"|"medium"|"long" }) => post<any>("/kiosk/book", payload),
  operatorAlert: (payload: { message: string; alert_type?: string; reservation_id?: string; room_id?: string }) => post<any>("/operator-alert", payload),
  telegramHealth: () => get<TelegramHealth>("/integrations/telegram/health"),
  adminUnlock: (pin: string) => post<{ token: string; ok: boolean }>("/admin/unlock", { pin }),
  adminValidate: (token: string) => post<{ valid: boolean }>("/admin/validate", { token }),
  checkin: (reservation_id: string) =>
    post<Reservation>("/checkin", { reservation_id }),
  checkout: (reservation_id: string) =>
    post<Reservation>("/checkout", { reservation_id }),
  updateRoomStatus: (room_id: string, status: string, notes?: string) =>
    fetch(`${MOTEL_API}/rooms/${room_id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, notes }),
    }).then((r) => r.json()),
};


export interface QaSummary {
  window_hours: number;
  total_runs: number;
  pass_count: number;
  fail_count: number;
  last_run: { ts: string; status: string; summary: string } | null;
  recent_failures: Array<{ ts: string; summary: string; log_tail: string }>;
}


export interface TelegramHealth { configured: boolean; has_bot_token: boolean; has_chat_id: boolean; }
export interface KioskLookupMatch { reservation_id: string; guest_name: string; check_in: string; check_out: string; status: string; room_id: string; }


export interface DisplacementScoreResult {
  displacement_score: number;
  recommendation: "accept" | "review" | "decline";
  nights: number;
  estimated_revenue: number;
  avg_projected_occupancy_pct: number;
  protected_hit_count: number;
}

export async function getDisplacementScore(payload: {check_in: string; check_out: string; rate_per_night: number; protected_dates?: string[]}) {
  return post<{ ok: boolean; result: DisplacementScoreResult }>("/manager/medium-stay/pricing/displacement-score", payload);
}
