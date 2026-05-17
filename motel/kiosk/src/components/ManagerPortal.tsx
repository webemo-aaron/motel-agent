import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, ManagerStrategy, Stats, ManagerPlan, WeeklyBriefing, ManagerRecommendations, ManagerAutomationSettings, RateSummary, DisplacementScoreResult, getDisplacementScore } from "../lib/api";

interface Props { stats: Stats | null }
const stages = ["new", "qualified", "proposal", "won", "lost"];

export default function ManagerPortal({ stats }: Props) {
  const [strategy, setStrategy] = useState<ManagerStrategy | null>(null);
  const [plan, setPlan] = useState<ManagerPlan | null>(null);
  const [briefing, setBriefing] = useState<WeeklyBriefing | null>(null);
  const [recs, setRecs] = useState<ManagerRecommendations | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exportUrl, setExportUrl] = useState<string>("");
  const [automation, setAutomation] = useState<ManagerAutomationSettings>({ auto_recovery_enabled: true, recovery_threshold_pct: 35, auto_briefing_alert_enabled: false });
  const [automationRuns, setAutomationRuns] = useState<Array<{ date: string; occupancy_pct: number; actions: Array<{ type: string }> }>>([]);
  const [qaSummary, setQaSummary] = useState<any | null>(null);
  const [rateSummary, setRateSummary] = useState<RateSummary | null>(null);
  const [telegramHealth, setTelegramHealth] = useState<{ configured: boolean; has_bot_token: boolean; has_chat_id: boolean } | null>(null);
  const [telegramTestStatus, setTelegramTestStatus] = useState<string>("");
  const [selectedLeadHistory, setSelectedLeadHistory] = useState<Array<{ date: string; stage: string; notes: string }>>([]);
  const [displacementScore, setDisplacementScore] = useState<DisplacementScoreResult | null>(null);

  const [campaign, setCampaign] = useState({ week: "Week 1", channel: "email", objective: "Direct bookings", offer: "2-night bundle", budget: 150, owner: "manager", status: "planned" });
  const [event, setEvent] = useState({ date: new Date().toISOString().slice(0,10), title: "Reunion Weekend", event_type: "reunion", expected_guests: 18, room_block: 8, notes: "House + kitchen access", status: "planned" });
  const [lead, setLead] = useState({ name: "", segment: "wedding", contact: "", source: "partner", est_value: 1200, stage: "new", notes: "" });
  const [ebike, setEbike] = useState({ fleet_size: 6, half_day_rate: 55, full_day_rate: 85 });
  const [bikeBooking, setBikeBooking] = useState({ guest_name: "", date: new Date().toISOString().slice(0,10), duration: "half_day", bikes: 2, status: "reserved" });

  useEffect(() => {
    if (!window.location.hash) return;
    const id = window.location.hash.replace('#', '');
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [plan]);

  async function refreshAll() {
    try {
      const [s, p, b, r, a, logs, rates] = await Promise.all([api.managerStrategy(), api.managerPlan(), api.weeklyBriefing(), api.managerRecommendations(), api.automationSettings(), api.automationLogs(), api.ratesSummary()]);
      setStrategy(s); setPlan(p); setBriefing(b); setRecs(r); setAutomation(a); setAutomationRuns(logs.logs ?? []); setRateSummary(rates);
      if (p.ebike?.settings) setEbike(p.ebike.settings);
      setError(null);
    } catch (e) { setError(e instanceof Error ? e.message : "Failed to load manager portal"); }
    finally { setLoading(false); }
  }

  useEffect(() => { void refreshAll(); }, []);

  const pipeline = useMemo(() => {
    const base: Record<string, number> = { new: 0, qualified: 0, proposal: 0, won: 0, lost: 0 };
    plan?.leads.forEach((l) => { base[l.stage] = (base[l.stage] ?? 0) + 1; });
    return base;
  }, [plan]);

  const eventsByMonth = useMemo(() => {
    const map: Record<string, Array<{ id: string; date: string; title: string; room_block: number }>> = {};
    (plan?.events ?? []).forEach((ev) => {
      const m = ev.date.slice(0, 7);
      map[m] = map[m] ?? [];
      map[m].push(ev);
    });
    return map;
  }, [plan]);

  async function sendTelegramTest() {
    setTelegramTestStatus("Sending...");
    try {
      const r = await api.operatorAlert({ message: "Manager portal Telegram test alert", alert_type: "urgent" });
      const sent = r?.telegram?.sent ? "sent" : "queued/local-only";
      setTelegramTestStatus(`Test alert created (${sent})`);
      const th = await api.telegramHealth();
      setTelegramHealth(th);
    } catch (e: any) {
      setTelegramTestStatus(`Failed: ${e?.message || 'unknown error'}`);
    }
  }

  if (loading) return <div className="text-slate-300">Loading manager portal...</div>;
  if (error || !strategy || !plan) return <div className="text-red-300">{error ?? "No data"}</div>;

  async function submitCampaign(e: FormEvent) { e.preventDefault(); await api.createCampaign(campaign); await refreshAll(); }
  async function submitEvent(e: FormEvent) { e.preventDefault(); await api.createEvent(event); await refreshAll(); }
  async function submitLead(e: FormEvent) { e.preventDefault(); await api.createLead(lead); setLead({ ...lead, name: "", contact: "", notes: "" }); await refreshAll(); }
  async function saveEbike(e: FormEvent) { e.preventDefault(); await api.setEbikeSettings(ebike); await refreshAll(); }
  async function submitBikeBooking(e: FormEvent) { e.preventDefault(); await api.createEbikeBooking(bikeBooking); setBikeBooking({ ...bikeBooking, guest_name: "" }); await refreshAll(); }
  async function moveLead(id: string, stage: string) { await api.updateLead(id, { stage }); await refreshAll(); }

  return (
    <div className="space-y-6">
      <section className="bg-slate-800/70 border border-slate-700 rounded p-4">
        <h2 className="text-xl font-semibold text-white mb-2">Manager Growth + Events Portal</h2>
        <p className="text-slate-300">Phase <span className="text-emerald-300 font-semibold">{strategy.strategy_phase}</span> · Occupancy {strategy.occupancy_pct.toFixed(1)}% · Revenue ${stats?.revenue_today.toFixed(2) ?? "0.00"}</p>
      </section>


      <section className="bg-slate-900 border border-slate-700 rounded p-3">
        <div className="text-xs uppercase tracking-wide text-slate-500 mb-2">Manager Submenu</div>
        <div className="flex flex-wrap gap-2 text-sm">
          <a href="#campaigns" className="bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded">Advertising and Campaigns</a>
          <a href="#events" className="bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded">Events</a>
          <a href="#groups" className="bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded">Groups and Leads</a>
        </div>
      </section>

      <section className="grid md:grid-cols-3 gap-3">
        <div className="bg-slate-900 border border-slate-700 rounded p-4">
          <div className="text-xs text-slate-400">Immediate Actions</div>
          <div className="mt-2 text-2xl font-semibold text-amber-300">{qaSummary?.fail_count ?? 0}</div>
          <div className="text-xs text-slate-300">QA failures needing review</div>
        </div>
        <div className="bg-slate-900 border border-slate-700 rounded p-4">
          <div className="text-xs text-slate-400">Housekeeping Priority</div>
          <div className="mt-2 text-2xl font-semibold text-rose-300">{Math.max(0, Math.round(100 - (strategy?.occupancy_pct ?? 0)))}</div>
          <div className="text-xs text-slate-300">Open capacity (%)</div>
        </div>
        <div className="bg-slate-900 border border-slate-700 rounded p-4">
          <div className="text-xs text-slate-400">System Health</div>
          <div className="mt-2 text-2xl font-semibold text-emerald-300">{qaSummary ? `${qaSummary.pass_count}/${qaSummary.total_runs}` : '...'} </div>
          <div className="text-xs text-slate-300">Portal QA pass ratio (24h)</div>
        </div>
      </section>

      {briefing && (

        <section className="bg-slate-900 border border-slate-700 rounded p-4">
          <div className="flex items-center justify-between mb-2"><h3 className="text-white font-semibold">Auto Weekly Manager Briefing</h3><button onClick={()=>void api.sendWeeklyBriefing()} className="bg-rose-600 px-3 py-1 rounded text-xs">Send to Operator Alert Queue</button></div>
          <pre className="text-xs whitespace-pre-wrap text-slate-200">{briefing.briefing}</pre>
          <ul className="list-disc ml-5 text-amber-300 text-sm">{briefing.actions.map((a)=><li key={a}>{a}</li>)}</ul>
        </section>
      )}






      {rateSummary && (
        <section className="bg-slate-900 border border-slate-700 rounded p-4">
          <h3 className="text-white font-semibold mb-2">Rate Management Integration (No Duplicate Build)</h3>
          <div className="text-sm text-slate-300">Snapshot rows: <span className="text-emerald-300">{rateSummary.snapshot_count}</span> · Alert rows: <span className="text-amber-300">{rateSummary.alerts_count}</span></div>
          <div className="grid md:grid-cols-2 gap-3 mt-2 text-xs">
            <div>
              <div className="text-emerald-300 mb-1">Sample Snapshot</div>
              <pre className="bg-slate-800 rounded p-2 overflow-auto max-h-28">{JSON.stringify(rateSummary.sample_snapshot, null, 2)}</pre>
            </div>
            <div>
              <div className="text-amber-300 mb-1">Sample Alerts</div>
              <pre className="bg-slate-800 rounded p-2 overflow-auto max-h-28">{JSON.stringify(rateSummary.sample_alerts, null, 2)}</pre>
            </div>
          </div>
        </section>
      )}


      <section className="bg-slate-900 border border-slate-700 rounded p-4">
        <h3 className="text-white font-semibold mb-2">Portal QA Summary (24h)</h3>
        {!qaSummary ? (
          <div className="text-slate-400 text-sm">Loading...</div>
        ) : (
          <div className="text-sm text-slate-200 space-y-1">
            <div>Total runs: {qaSummary.total_runs} | Pass: {qaSummary.pass_count} | Fail: {qaSummary.fail_count}</div>
            <div>Last run: {qaSummary.last_run ? `${qaSummary.last_run.ts} (${qaSummary.last_run.status})` : 'n/a'}</div>
            {qaSummary.recent_failures?.length > 0 && (
              <details className="mt-2">
                <summary className="cursor-pointer">Recent failures ({qaSummary.recent_failures.length})</summary>
                <ul className="mt-2 space-y-2 text-xs">
                  {qaSummary.recent_failures.map((f: any, idx: number) => (
                    <li key={idx} className="bg-slate-800 rounded p-2">
                      <div>{f.ts} — {f.summary}</div>
                      <pre className="whitespace-pre-wrap text-slate-300">{f.log_tail}</pre>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        )}
      </section>

      <section className="bg-slate-900 border border-slate-700 rounded p-4">
        <h3 className="text-white font-semibold mb-2">Automation Control Center</h3>
        <div className="grid md:grid-cols-3 gap-2 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" checked={automation.auto_recovery_enabled} onChange={(e)=>setAutomation({...automation, auto_recovery_enabled:e.target.checked})} /> Auto recovery</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={automation.auto_briefing_alert_enabled} onChange={(e)=>setAutomation({...automation, auto_briefing_alert_enabled:e.target.checked})} /> Auto briefing alert</label>
          <label className="flex items-center gap-2">Threshold % <input type="number" className="bg-slate-800 p-1 rounded w-20" value={automation.recovery_threshold_pct} onChange={(e)=>setAutomation({...automation, recovery_threshold_pct:Number(e.target.value)})} /></label>
        </div>
        <div className="flex gap-2 mt-2">
          <button className="bg-indigo-600 px-3 py-1 rounded text-sm" onClick={async ()=>{await api.saveAutomationSettings(automation); await refreshAll();}}>Save Automation Settings</button>
          <button className="bg-fuchsia-700 px-3 py-1 rounded text-sm" onClick={async ()=>{await api.runAutomationDaily(); await refreshAll();}}>Run Daily Automation Now</button>
        </div>
        <ul className="mt-3 text-xs text-slate-300 max-h-24 overflow-auto">
          {automationRuns.slice().reverse().map((run, idx)=><li key={idx}>• {run.date} occ {run.occupancy_pct}% actions: {(run.actions||[]).map(a=>a.type).join(', ') || 'none'}</li>)}
        </ul>
      </section>

      <section className="bg-slate-900 border border-slate-700 rounded p-4">
        <h3 className="text-white font-semibold mb-2">Command Center Actions</h3>
        <div className="flex flex-wrap gap-2">
          <button className="bg-amber-600 px-3 py-1 rounded text-sm" onClick={async ()=>{await api.triggerRecoverySprint(); await refreshAll();}}>Trigger Recovery Sprint</button>
          <button className="bg-cyan-700 px-3 py-1 rounded text-sm" onClick={async ()=>{const payload = await api.managerWeeklyExport(); const blob = new Blob([JSON.stringify(payload, null, 2)], {type:'application/json'}); const url = URL.createObjectURL(blob); setExportUrl(url);}}>Build Weekly JSON Export</button>
          {exportUrl && <a className="bg-emerald-700 px-3 py-1 rounded text-sm" href={exportUrl} download="manager-weekly-export.json">Download Export</a>}
        </div>
      </section>

      {recs && (
        <section className="bg-slate-900 border border-slate-700 rounded p-4">
          <h3 className="text-white font-semibold mb-2">AI Manager Recommendations</h3>
          <div className="text-xs text-slate-300 mb-2">Funnel — new:{recs.funnel.new} qualified:{recs.funnel.qualified} proposal:{recs.funnel.proposal} won:{recs.funnel.won} lost:{recs.funnel.lost}</div>
          <ul className="text-sm text-slate-200 list-disc ml-5">
            {recs.recommendations.map((r, i)=><li key={i}><span className="text-amber-300">[{r.priority}]</span> {r.item}</li>)}
          </ul>
        </section>
      )}

      <section id="campaigns" className="space-y-3">
        <div className="bg-slate-800/50 border border-slate-700 rounded p-3">
          <h3 className="text-white font-semibold">Advertising & Campaigns Workspace</h3>
          <p className="text-xs text-slate-300">Plan offers, channels, and campaign execution cadence.</p>
        </div>
        <div className="grid md:grid-cols-2 gap-4">
        <div className="bg-slate-900 border border-slate-700 rounded p-4">
          <h3 className="text-white font-semibold mb-2">Campaign Planner</h3>
          <form onSubmit={submitCampaign} className="space-y-2 text-sm">
            <input className="w-full bg-slate-800 p-2 rounded" value={campaign.week} onChange={(e)=>setCampaign({...campaign,week:e.target.value})} placeholder="Week" />
            <input className="w-full bg-slate-800 p-2 rounded" value={campaign.channel} onChange={(e)=>setCampaign({...campaign,channel:e.target.value})} placeholder="Channel" />
            <input className="w-full bg-slate-800 p-2 rounded" value={campaign.offer} onChange={(e)=>setCampaign({...campaign,offer:e.target.value})} placeholder="Offer" />
            <button className="bg-emerald-600 px-3 py-1 rounded">Add Campaign</button>
          </form>
          <ul className="mt-3 text-slate-200 text-sm space-y-1 max-h-36 overflow-auto">{plan.campaigns.map((c)=><li key={c.id}>• {c.week} {c.channel}: {c.offer}</li>)}</ul>
        </div>
        <div className="bg-slate-900 border border-slate-700 rounded p-4">
          <h3 id="events" className="text-white font-semibold mb-2">Events Workspace</h3>
          <p className="text-xs text-slate-300 mb-2">Coordinate room blocks, guest counts, and partner events.</p>
          <form onSubmit={submitEvent} className="space-y-2 text-sm">
            <input type="date" className="w-full bg-slate-800 p-2 rounded" value={event.date} onChange={(e)=>setEvent({...event,date:e.target.value})} />
            <input className="w-full bg-slate-800 p-2 rounded" value={event.title} onChange={(e)=>setEvent({...event,title:e.target.value})} placeholder="Event title" />
            <div className="grid grid-cols-2 gap-2">
              <input className="bg-slate-800 p-2 rounded" value={event.event_type} onChange={(e)=>setEvent({...event,event_type:e.target.value})} placeholder="Type" />
              <input type="number" className="bg-slate-800 p-2 rounded" value={event.room_block} onChange={(e)=>setEvent({...event,room_block:Number(e.target.value)})} placeholder="Room block" />
            </div>
            <button className="bg-blue-600 px-3 py-1 rounded">Add Event</button>
          </form>
          <div className="mt-3 max-h-44 overflow-auto text-sm text-slate-200 space-y-2">
            {Object.entries(eventsByMonth).map(([month, events]) => (
              <div key={month}><div className="text-emerald-300">{month}</div>{events.map((ev)=><div key={ev.id}>• {ev.date} {ev.title} ({ev.room_block} rooms)</div>)}</div>
            ))}
          </div>
        </div>
      </div>
      </section>

      <section id="groups" className="bg-slate-900 border border-slate-700 rounded p-4">
        <h3 className="text-white font-semibold mb-1">Groups & Leads Workspace</h3>
        <p className="text-xs text-slate-300 mb-3">Track group opportunities from inquiry to close.</p>
        <h4 className="text-white font-semibold mb-2">Lead Pipeline Kanban (drag/drop)</h4>
        <div className="grid md:grid-cols-5 gap-2 text-xs">
          {stages.map((stage) => (
            <div key={stage} className="bg-slate-800 rounded p-2"
              onDragOver={(e)=>e.preventDefault()}
              onDrop={(e)=>{const id=e.dataTransfer.getData('text/plain'); void moveLead(id, stage);}}>
              <div className="text-emerald-300 font-semibold mb-1">{stage} ({pipeline[stage] ?? 0})</div>
              <div className="space-y-1 min-h-12">
                {plan.leads.filter((l)=>l.stage===stage).map((l)=>(
                  <div key={l.id} draggable onClick={async ()=>{ const h = await api.leadHistory(l.id); setSelectedLeadHistory(h.history); }} onDragStart={(e)=>e.dataTransfer.setData('text/plain', l.id)} className="bg-slate-700 rounded p-1 cursor-grab">
                    {l.name}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
        <form onSubmit={submitLead} className="space-y-2 text-sm mt-3">
          <input className="w-full bg-slate-800 p-2 rounded" value={lead.name} onChange={(e)=>setLead({...lead,name:e.target.value})} placeholder="Lead name" required />
          <div className="grid grid-cols-3 gap-2">
            <input className="bg-slate-800 p-2 rounded" value={lead.contact} onChange={(e)=>setLead({...lead,contact:e.target.value})} placeholder="Contact" />
            <input className="bg-slate-800 p-2 rounded" value={lead.segment} onChange={(e)=>setLead({...lead,segment:e.target.value})} placeholder="Segment" />
            <button className="bg-purple-600 px-3 py-1 rounded">Add Lead</button>
          </div>
        </form>
      </section>


      <section className="bg-slate-900 border border-slate-700 rounded p-4">
        <h3 className="text-white font-semibold mb-2">Lead History Timeline</h3>
        {selectedLeadHistory.length === 0 ? (
          <p className="text-slate-400 text-sm">Click a lead card in the Kanban board to view stage history.</p>
        ) : (
          <ul className="text-sm text-slate-200 space-y-1">
            {selectedLeadHistory.map((h, idx)=><li key={`${h.date}-${idx}`}>• {h.date} — {h.stage}{h.notes ? ` (${h.notes})` : ""}</li>)}
          </ul>
        )}
      </section>

      <section className="bg-slate-900 border border-slate-700 rounded p-4">
        <h3 className="text-white font-semibold mb-2">Aventon E-Bike Ops Panel</h3>
        <form onSubmit={saveEbike} className="grid grid-cols-3 gap-2 text-sm">
          <input type="number" className="bg-slate-800 p-2 rounded" value={ebike.fleet_size} onChange={(e)=>setEbike({...ebike,fleet_size:Number(e.target.value)})} />
          <input type="number" className="bg-slate-800 p-2 rounded" value={ebike.half_day_rate} onChange={(e)=>setEbike({...ebike,half_day_rate:Number(e.target.value)})} />
          <input type="number" className="bg-slate-800 p-2 rounded" value={ebike.full_day_rate} onChange={(e)=>setEbike({...ebike,full_day_rate:Number(e.target.value)})} />
          <button className="bg-emerald-600 px-3 py-1 rounded col-span-3">Save Fleet/Rates</button>
        </form>
        <form onSubmit={submitBikeBooking} className="space-y-2 text-sm mt-3">
          <input className="w-full bg-slate-800 p-2 rounded" value={bikeBooking.guest_name} onChange={(e)=>setBikeBooking({...bikeBooking,guest_name:e.target.value})} placeholder="Guest name" required />
          <div className="grid grid-cols-3 gap-2">
            <input type="date" className="bg-slate-800 p-2 rounded" value={bikeBooking.date} onChange={(e)=>setBikeBooking({...bikeBooking,date:e.target.value})} />
            <select className="bg-slate-800 p-2 rounded" value={bikeBooking.duration} onChange={(e)=>setBikeBooking({...bikeBooking,duration:e.target.value})}><option value="half_day">half_day</option><option value="full_day">full_day</option></select>
            <input type="number" className="bg-slate-800 p-2 rounded" value={bikeBooking.bikes} onChange={(e)=>setBikeBooking({...bikeBooking,bikes:Number(e.target.value)})} min={1} />
          </div>
          <button className="bg-blue-600 px-3 py-1 rounded">Add Bike Booking</button>
        </form>
        <ul className="mt-3 text-slate-200 text-sm space-y-1 max-h-32 overflow-auto">{plan.ebike.bookings.map((b)=><li key={b.id} className="flex items-center justify-between gap-2"><span>• {b.date} {b.guest_name} ({b.bikes} bikes, {b.duration})</span><button className="text-xs bg-rose-700 px-2 py-0.5 rounded" onClick={async ()=>{await api.deleteEbikeBooking(b.id); await refreshAll();}}>Delete</button></li>)}</ul>
      </section>
      <section className="bg-slate-900 border border-slate-700 rounded p-4">
        <h3 className="text-lg font-semibold mb-2">Integrations: Telegram</h3>
        <div className="text-sm text-slate-300">
          Configured: <span className={telegramHealth?.configured ? "text-emerald-400" : "text-amber-400"}>{telegramHealth?.configured ? "Yes" : "No"}</span>
          {telegramHealth && (
            <span className="ml-2">(bot token: {telegramHealth.has_bot_token ? "ok" : "missing"}, chat id: {telegramHealth.has_chat_id ? "ok" : "missing"})</span>
          )}
        </div>
        <button className="mt-3 bg-blue-600 px-3 py-1 rounded" onClick={sendTelegramTest}>Send Test Telegram Alert</button>
        {telegramTestStatus && <div className="text-xs text-slate-400 mt-2">{telegramTestStatus}</div>}
      </section>

    </div>
  );
}
