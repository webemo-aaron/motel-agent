import { useEffect, useMemo, useState } from "react";
import { api, RateAlertItem, CompetitorCard } from "../lib/api";

type Timeframe = "7d" | "30d" | "90d" | "365d";

function daysFor(tf: Timeframe) {
  return tf === "7d" ? 7 : tf === "30d" ? 30 : tf === "90d" ? 90 : 365;
}

function withinDays(stayDate: string, d: number) {
  if (!stayDate) return false;
  const now = new Date();
  const dt = new Date(stayDate + "T00:00:00");
  const diff = (dt.getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
  return diff >= 0 && diff <= d;
}

function freshnessLabel(lastSeen: string) {
  if (!lastSeen) return { label: 'unknown', cls: 'text-slate-500' };
  const t = new Date(lastSeen).getTime();
  if (!Number.isFinite(t)) return { label: 'unknown', cls: 'text-slate-500' };
  const ageHrs = (Date.now() - t) / (1000 * 60 * 60);
  if (ageHrs <= 6) return { label: 'fresh', cls: 'text-emerald-400' };
  if (ageHrs <= 24) return { label: 'stale', cls: 'text-amber-400' };
  return { label: 'old', cls: 'text-rose-400' };
}

function alertDeltaPct(a: RateAlertItem): number {
  const raw = (a as any).delta_pct ?? (a as any).change_pct ?? (a as any).pct_change ?? 0;
  const n = Number(raw);
  return Number.isFinite(n) ? n : 0;
}


function round5(x: number) { return Math.round(x / 5) * 5; }
function boundedRate(rate: number, base: number) {
  const lo = base * 0.85;
  const hi = base * 1.60;
  return Math.min(Math.max(rate, lo), hi);
}
function calcRecommended(base: number, occMult: number, dowMult: number, leadMult: number) {
  return round5(boundedRate(base * occMult * dowMult * leadMult, base));
}

export default function RateIntelligence() {
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [snapshot, setSnapshot] = useState<Array<Record<string, unknown>>>([]);
  const [alerts, setAlerts] = useState<RateAlertItem[]>([]);
  const [competitors, setCompetitors] = useState<CompetitorCard[]>([]);
  const [calendar, setCalendar] = useState<{ from: string | null; to: string | null; days: string[]; local_events: Array<Record<string, unknown>> } | null>(null);
  const [market, setMarket] = useState<string>("all");
  const [timeframe, setTimeframe] = useState<Timeframe>("30d");
  const [confidenceFilter, setConfidenceFilter] = useState<"all"|"high_only">("all");
  const [busy, setBusy] = useState(false);
  const [qaSummary, setQaSummary] = useState<any | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastRefreshAt, setLastRefreshAt] = useState<string>("");
  const [briefingStatus, setBriefingStatus] = useState<string>("");
  const [publishStatus, setPublishStatus] = useState<string>("");

  const [baseRates, setBaseRates] = useState<{ SQ: number; DF: number; DQ: number; Hostel: number }>({ SQ: 109, DF: 139, DQ: 159, Hostel: 39 });
  const [leadWindow, setLeadWindow] = useState<'0-2 days'|'3-13 days'|'14+ days'>('0-2 days');
  const [weekendMode, setWeekendMode] = useState<boolean>(true);

  async function refresh() {
    const days = daysFor(timeframe);
    const [h, s, a, c, q, comp] = await Promise.all([
      api.ratesHealth(),
      api.ratesSnapshot(400),
      api.ratesAlerts(300),
      api.ratesCalendar(),
      api.qaSummary(24),
      api.ratesCompetitors(days, market),
    ]);
    setHealth(h);
    setSnapshot(s.items ?? []);
    setAlerts(a.items ?? []);
    setCalendar(c);
    setQaSummary(q);
    setCompetitors(comp.items ?? []);
    setLastRefreshAt(new Date().toISOString());
  }

  useEffect(() => { void refresh(); }, [timeframe, market]);

  useEffect(() => {
    if (!autoRefresh) return;
    const t = setInterval(() => { void refresh(); }, 60_000);
    return () => clearInterval(t);
  }, [autoRefresh, timeframe, market]);


  useEffect(() => {
    try {
      const raw = localStorage.getItem('motel_rate_base_rates');
      if (raw) {
        const parsed = JSON.parse(raw);
        setBaseRates({
          SQ: Number(parsed.SQ ?? 109),
          DF: Number(parsed.DF ?? 139),
          DQ: Number(parsed.DQ ?? 159),
          Hostel: Number(parsed.Hostel ?? 39),
        });
      }
    } catch {}
  }, []);

  useEffect(() => {
    localStorage.setItem('motel_rate_base_rates', JSON.stringify(baseRates));
  }, [baseRates]);

  const markets = useMemo(() => {
    const set = new Set<string>();
    [...snapshot, ...alerts].forEach((r) => {
      const m = String(r.market ?? "").trim();
      if (m) set.add(m);
    });
    return ["all", ...Array.from(set).sort()];
  }, [snapshot, alerts]);

  const windowDays = daysFor(timeframe);

  const snapshotFiltered = useMemo(() => {
    const byMarket = market === "all" ? snapshot : snapshot.filter((r) => String(r.market ?? "") === market);
    return byMarket.filter((r) => withinDays(String(r.stay_date ?? r.check_in ?? ""), windowDays));
  }, [snapshot, market, windowDays]);

  const alertsFiltered = useMemo(() => {
    const byMarket = market === "all" ? alerts : alerts.filter((r) => String(r.market ?? "") === market);
    return byMarket.filter((r) => withinDays(String((r as any).stay_date ?? (r as any).check_in ?? ""), windowDays));
  }, [alerts, market, windowDays]);

  const competitorCards = useMemo(
    () => competitors.filter(c => confidenceFilter === 'all' ? true : c.confidence === 'high').slice(0, 8),
    [competitors, confidenceFilter]
  );

  const unackedCount = useMemo(() => alertsFiltered.filter(a => !a.acknowledged).length, [alertsFiltered]);
  const highVolatilityCount = useMemo(() => alertsFiltered.filter(a => Math.abs(alertDeltaPct(a)) >= 10).length, [alertsFiltered]);

  const recommendedRates = useMemo(() => {
    const occ = Number((health as any)?.occupancy_pct ?? 20);
    const occMult = occ < 35 ? 0.9 : occ <= 60 ? 1.0 : occ <= 80 ? 1.15 : 1.3;
    const dowMult = weekendMode ? 1.2 : 1.0;
    const leadMult = leadWindow === '14+ days' ? 0.95 : leadWindow === '3-13 days' ? 1.0 : 1.1;
    return {
      SQ: calcRecommended(baseRates.SQ, occMult, dowMult, leadMult),
      DF: calcRecommended(baseRates.DF, occMult, dowMult, leadMult),
      DQ: calcRecommended(baseRates.DQ, occMult, dowMult, leadMult),
      Hostel: calcRecommended(baseRates.Hostel, occMult, dowMult, leadMult),
      occ,
      occMult,
      dowMult,
      leadMult,
    };
  }, [baseRates, health, weekendMode, leadWindow]);

  async function acknowledge(alertId: string) {
    setBusy(true);
    try {
      await api.acknowledgeRateAlert(alertId);
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function sendRateBriefing() {
    setBriefingStatus('sending...');
    try {
      const msg = [
        `Rate Briefing (${market}, ${timeframe})`,
        `Unacknowledged alerts: ${unackedCount}`,
        `High volatility alerts (>=10%): ${highVolatilityCount}`,
        `Competitor cards in view: ${competitorCards.length}`,
        `Snapshot rows in window: ${snapshotFiltered.length}`,
      ].join(' | ');
      const res = await api.operatorAlert({ message: msg, alert_type: 'complaint' });
      setBriefingStatus(res?.status === 'queued_local_only' ? 'queued (local only)' : 'sent');
    } catch {
      setBriefingStatus('failed');
    }
  }


  async function publishSuggestedRates() {
    setPublishStatus('publishing...');
    try {
      const msg = [
        `Suggested Rates (${market}, ${timeframe}, ${weekendMode ? 'weekend' : 'weekday'}, ${leadWindow})`,
        `SQ $${recommendedRates.SQ}`,
        `DF $${recommendedRates.DF}`,
        `DQ $${recommendedRates.DQ}`,
        `Hostel/bed $${recommendedRates.Hostel}`,
      ].join(' | ');
      const res = await api.operatorAlert({ message: msg, alert_type: 'urgent' });
      setPublishStatus(res?.status === 'queued_local_only' ? 'queued (local only)' : 'published');
    } catch {
      setPublishStatus('failed');
    }
  }

  return (
    <div className="space-y-4">
      <section className="bg-slate-900 border border-slate-700 rounded p-4">
        <h2 className="text-xl text-white font-semibold">Rate Intelligence</h2>
        <div className="mt-2 text-sm text-slate-300">Competitors first view + timeframe filtering for tactical pricing reads.</div>
        <div className="mt-3 flex flex-wrap gap-3 items-center">
          <label className="text-sm">Market</label>
          <select aria-label="Market" className="bg-slate-800 rounded px-2 py-1" value={market} onChange={(e)=>setMarket(e.target.value)}>
            {markets.map((m)=><option key={m} value={m}>{m}</option>)}
          </select>
          <label className="text-sm">Confidence</label>
          <select aria-label="Confidence" className="bg-slate-800 rounded px-2 py-1" value={confidenceFilter} onChange={(e)=>setConfidenceFilter(e.target.value as any)}>
            <option value="all">All sources</option>
            <option value="high_only">High confidence only</option>
          </select>
          <label className="text-sm">Timeframe</label>
          <select aria-label="Timeframe" className="bg-slate-800 rounded px-2 py-1" value={timeframe} onChange={(e)=>setTimeframe(e.target.value as Timeframe)}>
            <option value="7d">Next 7 days</option>
            <option value="30d">Next 30 days</option>
            <option value="90d">Next 90 days</option>
            <option value="365d">Next 365 days</option>
          </select>
        </div>
      </section>

      <section className="bg-slate-900 border border-slate-700 rounded p-4" data-testid="rate-ops-panel">
        <h3 className="text-white font-semibold mb-2">Operational Controls</h3>
        <div className="grid md:grid-cols-4 gap-3 text-sm">
          <div className="bg-slate-800 rounded p-2"><div className="text-slate-400 text-xs">Unacknowledged Alerts</div><div className="text-amber-300 text-lg font-semibold">{unackedCount}</div></div>
          <div className="bg-slate-800 rounded p-2"><div className="text-slate-400 text-xs">High Volatility (≥10%)</div><div className="text-rose-300 text-lg font-semibold">{highVolatilityCount}</div></div>
          <div className="bg-slate-800 rounded p-2"><div className="text-slate-400 text-xs">Last Refresh</div><div className="text-slate-200 text-xs">{lastRefreshAt ? new Date(lastRefreshAt).toLocaleString() : 'n/a'}</div></div>
          <div className="bg-slate-800 rounded p-2"><div className="text-slate-400 text-xs">Auto Refresh</div><div className="text-slate-200">{autoRefresh ? 'On (60s)' : 'Off'}</div></div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2 items-center">
          <button className="bg-indigo-600 hover:bg-indigo-500 px-3 py-1.5 rounded text-sm" onClick={()=>void refresh()}>Refresh now</button>
          <button className="bg-emerald-600 hover:bg-emerald-500 px-3 py-1.5 rounded text-sm" onClick={()=>setAutoRefresh(v=>!v)}>{autoRefresh ? 'Disable auto refresh' : 'Enable auto refresh'}</button>
          <button className="bg-cyan-700 hover:bg-cyan-600 px-3 py-1.5 rounded text-sm" onClick={()=>void sendRateBriefing()}>Send rate briefing</button>
          {briefingStatus && <span className="text-xs text-slate-300">Briefing status: {briefingStatus}</span>}
        </div>
      </section>


      <section className="bg-slate-900 border border-slate-700 rounded p-4" data-testid="rate-recommendations-panel">
        <h3 className="text-white font-semibold mb-2">Recommended Rates (Operational)</h3>
        <div className="grid md:grid-cols-4 gap-3 text-xs mb-3">
          {(['SQ','DF','DQ','Hostel'] as const).map((k) => (
            <label key={k} className="bg-slate-800 rounded p-2 text-slate-300">{k} Base
              <input aria-label={`${k} Base`} type="number" className="mt-1 w-full bg-slate-700 rounded px-2 py-1 text-slate-100" value={baseRates[k]}
                onChange={(e)=>setBaseRates((s)=>({ ...s, [k]: Number(e.target.value || 0) }))} />
            </label>
          ))}
        </div>
        <div className="flex flex-wrap gap-3 items-center text-sm mb-3">
          <label className="text-slate-300">Lead window
            <select aria-label="Lead Window" className="ml-2 bg-slate-800 rounded px-2 py-1" value={leadWindow} onChange={(e)=>setLeadWindow(e.target.value as any)}>
              <option>0-2 days</option><option>3-13 days</option><option>14+ days</option>
            </select>
          </label>
          <label className="text-slate-300">
            <input aria-label="Weekend Mode" type="checkbox" className="mr-2" checked={weekendMode} onChange={(e)=>setWeekendMode(e.target.checked)} />Weekend mode (Fri-Sat)
          </label>
          <div className="text-slate-400 text-xs">occ={recommendedRates.occ.toFixed(1)}% · occ×{recommendedRates.occMult} · dow×{recommendedRates.dowMult} · lead×{recommendedRates.leadMult}</div>
        </div>
        <div className="grid md:grid-cols-4 gap-3">
          <div className="bg-slate-800 rounded p-3"><div className="text-slate-400 text-xs">SQ</div><div className="text-2xl text-emerald-300 font-semibold">${recommendedRates.SQ}</div></div>
          <div className="bg-slate-800 rounded p-3"><div className="text-slate-400 text-xs">DF</div><div className="text-2xl text-emerald-300 font-semibold">${recommendedRates.DF}</div></div>
          <div className="bg-slate-800 rounded p-3"><div className="text-slate-400 text-xs">DQ</div><div className="text-2xl text-emerald-300 font-semibold">${recommendedRates.DQ}</div></div>
          <div className="bg-slate-800 rounded p-3"><div className="text-slate-400 text-xs">Hostel / bed</div><div className="text-2xl text-emerald-300 font-semibold">${recommendedRates.Hostel}</div></div>
        </div>
        <div className="mt-3 flex items-center gap-3">
          <button className="bg-fuchsia-700 hover:bg-fuchsia-600 px-3 py-1.5 rounded text-sm" onClick={()=>void publishSuggestedRates()}>Publish suggested rates</button>
          {publishStatus && <span className="text-xs text-slate-300">Publish status: {publishStatus}</span>}
        </div>
      </section>

      <section className="bg-slate-900 border border-slate-700 rounded p-4">
        <h3 className="text-white font-semibold mb-2">Top Competitor Signals ({competitorCards.length})</h3>
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-3">
          {competitorCards.map((c) => {
            const f = freshnessLabel(c.last_seen);
          
  async function publishSuggestedRates() {
    setPublishStatus('publishing...');
    try {
      const msg = [
        `Suggested Rates (${market}, ${timeframe}, ${weekendMode ? 'weekend' : 'weekday'}, ${leadWindow})`,
        `SQ $${recommendedRates.SQ}`,
        `DF $${recommendedRates.DF}`,
        `DQ $${recommendedRates.DQ}`,
        `Hostel/bed $${recommendedRates.Hostel}`,
      ].join(' | ');
      const res = await api.operatorAlert({ message: msg, alert_type: 'urgent' });
      setPublishStatus(res?.status === 'queued_local_only' ? 'queued (local only)' : 'published');
    } catch {
      setPublishStatus('failed');
    }
  }

  return (
              <div key={c.property} className="bg-slate-800 rounded p-3">
                <div className="text-slate-100 font-medium text-sm">{c.property}</div>
                <div className="text-xs text-slate-300 mt-1">Signals: {c.count}</div>
                <div className="text-xs text-slate-300">Median: {c.median_rate ? `$${c.median_rate}` : 'n/a'}</div>
                <div className="text-xs text-slate-300">Floor: {c.min_rate ? `$${c.min_rate}` : 'n/a'}</div>
                <div className="text-xs text-slate-400 mt-1">{(c.markets || []).filter(Boolean).join(', ')}</div>
                <div className="text-[10px] mt-1 text-slate-500">{(c.sources || []).join(' + ')} · confidence: {c.confidence}</div>
                <div className={`text-[10px] mt-0.5 ${f.cls}`}>freshness: {f.label}</div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="bg-slate-900 border border-slate-700 rounded p-4">
        <h3 className="text-white font-semibold mb-2">Portal QA Summary (24h)</h3>
        {!qaSummary ? <div className="text-slate-400 text-sm">Loading...</div> : (
          <div className="text-sm text-slate-200 space-y-1">
            <div>Total runs: {qaSummary.total_runs} | Pass: {qaSummary.pass_count} | Fail: {qaSummary.fail_count}</div>
            <div>Last run: {qaSummary.last_run ? `${qaSummary.last_run.ts} (${qaSummary.last_run.status})` : 'n/a'}</div>
          </div>
        )}
      </section>

      <section className="bg-slate-900 border border-slate-700 rounded p-4">
        <h3 className="text-white font-semibold mb-2">Pipeline Health</h3>
        <pre className="bg-slate-800 rounded p-2 text-xs overflow-auto max-h-40">{JSON.stringify(health, null, 2)}</pre>
      </section>

      <section className="bg-slate-900 border border-slate-700 rounded p-4">
        <h3 className="text-white font-semibold mb-2">Live Snapshot ({snapshotFiltered.length})</h3>
        <div className="overflow-auto max-h-80 text-xs">
          <table className="w-full">
            <thead><tr className="text-slate-300"><th className="text-left p-1">Property</th><th className="text-left p-1">Market</th><th className="text-left p-1">Stay Date</th><th className="text-left p-1">Rate</th><th className="text-left p-1">Tags</th><th className="text-left p-1">Last Seen</th></tr></thead>
            <tbody>
              {snapshotFiltered.slice(0,250).map((r, i)=>(
                <tr key={i} className="border-t border-slate-800"><td className="p-1">{String(r.property ?? "")}</td><td className="p-1">{String(r.market ?? "")}</td><td className="p-1">{String(r.stay_date ?? r.check_in ?? "")}</td><td className="p-1">{String(r.rate ?? r.nightly_rate ?? r.estimated_rate_usd ?? "")}</td><td className="p-1">{String(r.tags ?? r.season_tags ?? "")}</td><td className="p-1">{String(r.last_seen ?? r.timestamp ?? "")}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="bg-slate-900 border border-slate-700 rounded p-4">
        <h3 className="text-white font-semibold mb-2">Rate Change Feed ({alertsFiltered.length})</h3>
        <ul className="space-y-2 text-sm max-h-80 overflow-auto">
          {alertsFiltered.slice(0,250).map((a)=> (
            <li key={a.id} className="border border-slate-800 rounded p-2 flex items-center justify-between gap-2">
              <div>
                <div className="text-slate-100">{String((a as any).property ?? "")} · {String((a as any).stay_date ?? (a as any).check_in ?? "")} · {String((a as any).market ?? "")}</div>
                <div className="text-xs text-slate-400">Δ {String((a as any).delta_pct ?? (a as any).change_pct ?? (a as any).pct_change ?? "n/a")} · {String((a as any).direction ?? "")}</div>
              </div>
              <button disabled={busy || a.acknowledged} className="bg-indigo-600 disabled:bg-slate-700 px-2 py-1 rounded text-xs" onClick={()=>acknowledge(a.id)}>{a.acknowledged ? "Acknowledged" : "Acknowledge"}</button>
            </li>
          ))}
        </ul>
      </section>

      <section className="bg-slate-900 border border-slate-700 rounded p-4">
        <h3 className="text-white font-semibold mb-2">Market Calendar</h3>
        <div className="text-xs text-slate-300 mb-2">Range: {calendar?.from ?? "n/a"} → {calendar?.to ?? "n/a"} · Days: {(Array.isArray(calendar?.days) ? calendar!.days.length : 0)}</div>
        <div className="grid md:grid-cols-2 gap-3 text-xs">
          <pre className="bg-slate-800 rounded p-2 overflow-auto max-h-48">{JSON.stringify((Array.isArray(calendar?.days) ? calendar!.days : []).slice(0, 60), null, 2)}</pre>
          <pre className="bg-slate-800 rounded p-2 overflow-auto max-h-48">{JSON.stringify((Array.isArray(calendar?.local_events) ? calendar!.local_events : []).slice(0, 30), null, 2)}</pre>
        </div>
      </section>
    </div>
  );
}
