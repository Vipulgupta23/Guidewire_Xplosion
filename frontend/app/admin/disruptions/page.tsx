"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import dynamic from "next/dynamic";

const MapComponent = dynamic(() => import("@/components/admin/DisruptionMap"), { ssr: false });

interface LiveGrid {
  id: string;
  city: string;
  center_lat: number;
  center_lng: number;
  map_color: string;
  state_label: string;
  risk_percent: number;
  insured_worker_count: number;
  worker_count: number;
  active_disruption_count: number;
  premium_impact_label: string;
  trigger_origin?: string | null;
  feature_freshness?: {
    status: string;
    observed_at?: string;
    expires_at?: string;
  };
  feature_snapshot?: {
    rain_6h?: number;
    forecast_peak_rain_24h?: number;
    aqi?: number;
    heat_index?: number;
    traffic_risk?: number;
    flood_risk?: number;
    seasonal_factor?: number;
    predictive_risk_hours?: number;
    weather_description?: string;
  };
  active_disruptions?: Array<{
    id: string;
    trigger_type: string;
    severity: number;
    threshold: number;
    weather_description: string;
    started_at: string;
    raw_data?: Record<string, unknown>;
  }>;
}

interface TriggerResponse {
  message: string;
  disruption_id?: string;
  trigger_origin: string;
  duplicate: boolean;
  affected_worker_count: number;
  claims_created: number;
  auto_paid_claims: number;
  flagged_claims: number;
  manual_review_claims: number;
  paid_payouts: number;
  held_payouts: number;
  demo_note?: string | null;
}

const TRIGGER_OPTIONS = [
  { type: "heavy_rainfall", label: "Heavy Rainfall", severity: 58, badge: "🌧️" },
  { type: "extreme_heat", label: "Extreme Heat", severity: 46, badge: "🌡️" },
  { type: "severe_aqi", label: "Severe AQI", severity: 420, badge: "😷" },
  { type: "flood_alert", label: "Flood Alert", severity: 0.88, badge: "🌊" },
  { type: "platform_outage", label: "Platform Outage", severity: 1, badge: "📵" },
  { type: "curfew_bandh", label: "Curfew/Bandh", severity: 1, badge: "🚧" },
  { type: "cyclone_storm", label: "Cyclone/Storm", severity: 0.95, badge: "🌪️" },
];

export default function DisruptionsPage() {
  const [grids, setGrids] = useState<LiveGrid[]>([]);
  const [selectedGridId, setSelectedGridId] = useState<string | null>(null);
  const [cityFilter, setCityFilter] = useState<string>("All Cities");
  const [activeOnly, setActiveOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [triggeringType, setTriggeringType] = useState<string | null>(null);
  const [lastTriggerResult, setLastTriggerResult] = useState<TriggerResponse | null>(null);
  const [loadError, setLoadError] = useState<string>("");
  const [refreshingGrid, setRefreshingGrid] = useState(false);

  const fetchData = useCallback(async () => {
    const params = new URLSearchParams();
    if (cityFilter !== "All Cities") params.set("city", cityFilter);
    if (activeOnly) params.set("active_only", "true");
    try {
      const g = await api<LiveGrid[]>(`/microgrids/live?${params.toString()}`);
      setGrids(g);
      setSelectedGridId((current) => current && g.some((grid) => grid.id === current) ? current : g[0]?.id || null);
      setLoadError("");
    } catch (err) {
      console.error(err);
      setLoadError(err instanceof Error ? err.message : "Failed to load live grid map");
      setGrids([]);
      setSelectedGridId(null);
    }
    setLoading(false);
  }, [cityFilter, activeOnly]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const cities = useMemo(
    () => ["All Cities", ...Array.from(new Set(grids.map((grid) => grid.city))).sort()],
    [grids],
  );

  const selectedGrid = useMemo(
    () => grids.find((grid) => grid.id === selectedGridId) || null,
    [grids, selectedGridId],
  );

  const handleTrigger = async (triggerType: string, severity: number) => {
    if (!selectedGrid) return;
    setTriggeringType(triggerType);
    try {
      const result = await api<TriggerResponse>("/admin/simulate-trigger", {
        method: "POST",
        body: {
          trigger_type: triggerType,
          grid_id: selectedGrid.id,
          severity,
          description: `Admin simulated ${triggerType.replace(/_/g, " ")} in ${selectedGrid.city}`,
        },
      });
      setLastTriggerResult(result);
      await fetchData();
    } catch (err) {
      console.error(err);
    }
    setTriggeringType(null);
  };

  const handleRefreshSelectedGrid = async () => {
    if (!selectedGrid) return;
    setRefreshingGrid(true);
    try {
      await api(`/microgrids/${selectedGrid.id}/refresh-live`, { method: "POST" });
      await fetchData();
    } catch (err) {
      console.error(err);
    }
    setRefreshingGrid(false);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-10 h-10 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Live Disruption Map</h1>
          <p className="text-sm text-slate-400">
            Live weather/AQI grid view with click-to-trigger automation for protected riders.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={cityFilter}
            onChange={(e) => setCityFilter(e.target.value)}
            className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white"
          >
            {cities.map((city) => (
              <option key={city} value={city}>{city}</option>
            ))}
          </select>
          <label className="flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={activeOnly}
              onChange={(e) => setActiveOnly(e.target.checked)}
            />
            Active/insured only
          </label>
          <button onClick={fetchData} className="rounded-xl bg-amber-500 px-4 py-2 text-sm font-semibold text-slate-950">
            Refresh
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 overflow-hidden rounded-3xl border border-slate-800 bg-slate-950/70" style={{ height: "560px" }}>
          <MapComponent
            grids={grids}
            selectedGridId={selectedGridId}
            onSelectGrid={setSelectedGridId}
          />
        </div>

        <div className="space-y-4">
          {loadError && (
            <div className="glass-card border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-300">
              {loadError}
            </div>
          )}
          {selectedGrid ? (
            <>
              <div className="glass-card p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-xs uppercase tracking-wider text-slate-400">{selectedGrid.city}</p>
                    <h3 className="text-lg font-semibold text-white">{selectedGrid.id}</h3>
                    <p className="mt-1 text-sm text-slate-300">{selectedGrid.state_label}</p>
                  </div>
                  <span
                    className="rounded-full px-3 py-1 text-xs font-semibold"
                    style={{ backgroundColor: `${selectedGrid.map_color}22`, color: selectedGrid.map_color }}
                  >
                    {selectedGrid.risk_percent}% risk
                  </span>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                  <Metric label="Insured riders" value={String(selectedGrid.insured_worker_count)} />
                  <Metric label="All riders" value={String(selectedGrid.worker_count)} />
                  <Metric label="Rain 6h" value={`${Number(selectedGrid.feature_snapshot?.rain_6h || 0).toFixed(1)} mm`} />
                  <Metric label="AQI" value={`${Math.round(Number(selectedGrid.feature_snapshot?.aqi || 0))}`} />
                  <Metric label="Heat index" value={`${Number(selectedGrid.feature_snapshot?.heat_index || 0).toFixed(1)}°C`} />
                  <Metric label="Traffic risk" value={`${Math.round(Number(selectedGrid.feature_snapshot?.traffic_risk || 0) * 100)}%`} />
                  <Metric label="Flood risk" value={`${Math.round(Number(selectedGrid.feature_snapshot?.flood_risk || 0) * 100)}%`} />
                  <Metric label="Predictive hours" value={`${selectedGrid.feature_snapshot?.predictive_risk_hours || 0}h`} />
                </div>

                <div className="mt-4 rounded-2xl bg-slate-800/60 p-3 text-sm text-slate-300">
                  <p className="font-medium text-white">Premium impact</p>
                  <p className="mt-1">{selectedGrid.premium_impact_label}</p>
                  <p className="mt-2 text-xs text-slate-500">
                    Data freshness: {selectedGrid.feature_freshness?.status || "unknown"}
                  </p>
                  <button
                    onClick={handleRefreshSelectedGrid}
                    disabled={refreshingGrid}
                    className="mt-3 rounded-xl bg-cyan-500/15 px-3 py-2 text-xs font-semibold text-cyan-300 hover:bg-cyan-500/25 disabled:opacity-60"
                  >
                    {refreshingGrid ? "Refreshing grid..." : "Refresh this grid now"}
                  </button>
                </div>
              </div>

              <div className="glass-card p-4">
                <p className="mb-3 text-sm font-semibold text-white">Trigger this grid</p>
                <div className="grid grid-cols-1 gap-2">
                  {TRIGGER_OPTIONS.map((trigger) => (
                    <button
                      key={trigger.type}
                      onClick={() => handleTrigger(trigger.type, trigger.severity)}
                      disabled={triggeringType === trigger.type}
                      className="flex items-center justify-between rounded-xl border border-slate-700 bg-slate-900/70 px-3 py-3 text-left text-sm text-slate-200 hover:border-amber-500/60 disabled:opacity-60"
                    >
                      <span>{trigger.badge} {trigger.label}</span>
                      <span className="text-xs text-slate-500">
                        {trigger.type === "platform_outage" ? "manual only" : "fire"}
                      </span>
                    </button>
                  ))}
                </div>

                {lastTriggerResult && (
                  <div className="mt-4 rounded-2xl border border-cyan-500/20 bg-cyan-500/10 p-3 text-sm text-slate-200">
                    <p className="font-semibold text-white">{lastTriggerResult.message}</p>
                    <p className="mt-1 text-slate-300">
                      Riders affected: {lastTriggerResult.affected_worker_count} · Claims: {lastTriggerResult.claims_created}
                    </p>
                    <p className="text-slate-300">
                      Paid: {lastTriggerResult.paid_payouts} · Held: {lastTriggerResult.held_payouts} · Flagged: {lastTriggerResult.flagged_claims}
                    </p>
                    {lastTriggerResult.duplicate && (
                      <p className="mt-1 text-xs text-amber-300">This grid already had the same trigger in the current 6h window.</p>
                    )}
                    {lastTriggerResult.demo_note && (
                      <p className="mt-1 text-xs text-slate-400">{lastTriggerResult.demo_note}</p>
                    )}
                  </div>
                )}
              </div>

              <div className="glass-card p-4">
                <p className="mb-3 text-sm font-semibold text-white">
                  Active disruptions ({selectedGrid.active_disruption_count})
                </p>
                {selectedGrid.active_disruptions && selectedGrid.active_disruptions.length > 0 ? (
                  <div className="space-y-2">
                    {selectedGrid.active_disruptions.map((item) => (
                      <div key={item.id} className="rounded-xl border border-slate-700 bg-slate-900/70 p-3">
                        <div className="flex items-center justify-between gap-3">
                          <p className="text-sm font-medium capitalize text-white">{item.trigger_type.replace(/_/g, " ")}</p>
                          <span className="text-xs text-slate-400">
                            {(((item.raw_data || {}).trigger_origin as string) || "live_detected").replace(/_/g, " ")}
                          </span>
                        </div>
                        <p className="mt-1 text-xs text-slate-400">{item.weather_description}</p>
                        <p className="mt-1 text-xs text-slate-500">
                          {new Date(item.started_at).toLocaleString("en-IN", {
                            month: "short",
                            day: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-slate-400">No active disruption in this grid.</p>
                )}
              </div>
            </>
          ) : (
            <div className="glass-card p-6 text-center text-slate-400">
              {grids.length === 0
                ? "No live grids matched the current filter. Turn off Active/insured only or refresh after the backend reloads."
                : "Select a grid to inspect live risk and trigger automation."}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-slate-800/50 p-3">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="mt-1 text-sm font-medium text-white">{value}</p>
    </div>
  );
}
