"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import StatsBar from "@/components/admin/StatsBar";

interface Stats {
  total_workers: number;
  active_disruptions: number;
  claims_today: number;
  total_payout_today: number;
  fraud_alerts: number;
  active_policies: number;
  loss_ratio_percent: number;
  current_week_premium_total?: number;
  projected_next_week_loss_ratio?: number;
  telegram_status?: {
    linked: boolean;
  };
}

interface DailyStat {
  date: string;
  claims: number;
  payout: number;
}

interface PredictiveAnalytics {
  summary: {
    next_week_expected_claims: number;
    next_week_expected_payout_liability: number;
    high_risk_grid_count: number;
  };
  cities: Array<{
    city: string;
    grid_count: number;
    high_risk_grids: number;
    expected_claims: number;
    expected_payout_liability: number;
  }>;
  hotspots: Array<{
    grid_id: string;
    city: string;
    severity_label: string;
    expected_payout_liability: number;
  }>;
}

interface PayoutSummary {
  paid_total: number;
  held_total: number;
  paid_count: number;
  held_count: number;
  recent_payouts?: Array<{
    id: string;
    amount: number;
    status: string;
    mock_payout_id?: string;
    created_at: string;
  }>;
}

export default function AdminOverview() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [dailyStats, setDailyStats] = useState<DailyStat[]>([]);
  const [predictiveAnalytics, setPredictiveAnalytics] = useState<PredictiveAnalytics | null>(null);
  const [payoutSummary, setPayoutSummary] = useState<PayoutSummary | null>(null);
  const [telegramChatId, setTelegramChatId] = useState("");
  const [telegramMessage, setTelegramMessage] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const [s, d, predictive, payouts, notifStatus] = await Promise.all([
          api<Stats>("/admin/stats"),
          api<DailyStat[]>("/admin/daily-stats?days=7"),
          api<PredictiveAnalytics>("/admin/predictive-analytics"),
          api<PayoutSummary>("/admin/payouts-summary"),
          api<{ target_id?: string }>("/notifications/telegram/status/admin/default_admin"),
        ]);
        setStats(s);
        setDailyStats(d);
        setPredictiveAnalytics(predictive);
        setPayoutSummary(payouts);
        setTelegramChatId(
          notifStatus.target_id ||
            localStorage.getItem("telegram_chat_admin_default") ||
            "",
        );
      } catch (err) {
        console.error(err);
      }
      setLoading(false);
    };
    fetchStats();
    const interval = setInterval(fetchStats, 15000);
    return () => clearInterval(interval);
  }, []);

  if (loading || !stats) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-10 h-10 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const maxPayout = Math.max(...dailyStats.map(d => d.payout), 1);

  const handleLinkTelegram = async () => {
    try {
      await api("/notifications/telegram/link", {
        method: "POST",
        body: {
          entity_type: "admin",
          entity_id: "default_admin",
          chat_id: telegramChatId,
          username: "Operator",
        },
      });
      localStorage.setItem("telegram_chat_admin_default", telegramChatId);
      setTelegramMessage("Admin Telegram alerts linked");
    } catch (err) {
      setTelegramMessage(err instanceof Error ? err.message : "Failed to link Telegram");
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Dashboard Overview</h1>

      {/* Stats Row */}
      <StatsBar stats={stats} />

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="glass-card p-4">
          <p className="text-sm text-slate-400">Loss ratio today</p>
          <p className="mt-1 text-2xl font-bold text-amber-400">{stats.loss_ratio_percent?.toFixed?.(1) ?? stats.loss_ratio_percent}%</p>
        </div>
        <div className="glass-card p-4">
          <p className="text-sm text-slate-400">Held payouts</p>
          <p className="mt-1 text-2xl font-bold text-cyan-300">₹{payoutSummary?.held_total?.toFixed(0) || 0}</p>
        </div>
        <div className="glass-card p-4">
          <p className="text-sm text-slate-400">Next-week liability</p>
          <p className="mt-1 text-2xl font-bold text-red-300">₹{predictiveAnalytics?.summary.next_week_expected_payout_liability?.toFixed(0) || 0}</p>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="glass-card p-4">
          <p className="text-sm text-slate-400">Weekly premium pool</p>
          <p className="mt-1 text-2xl font-bold text-cyan-300">₹{stats.current_week_premium_total?.toFixed?.(0) || 0}</p>
        </div>
        <div className="glass-card p-4">
          <p className="text-sm text-slate-400">Projected loss ratio</p>
          <p className="mt-1 text-2xl font-bold text-orange-300">{stats.projected_next_week_loss_ratio?.toFixed?.(1) || 0}%</p>
        </div>
        <div className="glass-card p-4">
          <p className="text-sm text-slate-400">Telegram operator alerts</p>
          <p className="mt-1 text-2xl font-bold text-emerald-300">{stats.telegram_status?.linked ? "Live" : "Off"}</p>
        </div>
      </div>

      {/* Simple chart */}
      <div className="glass-card p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Last 7 Days — Claims & Payouts</h2>
        {dailyStats.length > 0 ? (
          <div className="space-y-3">
            {dailyStats.map((day, i) => (
              <div key={day.date} className="flex items-center gap-4 fade-in-up" style={{ animationDelay: `${i * 60}ms` }}>
                <span className="text-xs text-slate-400 w-16 shrink-0">
                  {new Date(day.date).toLocaleDateString("en-IN", { month: "short", day: "numeric" })}
                </span>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <div className="flex-1 h-4 bg-slate-700 rounded overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-amber-500 to-amber-600 rounded transition-all duration-500"
                        style={{ width: `${Math.max((day.payout / maxPayout) * 100, 2)}%` }}
                      />
                    </div>
                    <span className="text-xs text-amber-400 font-mono w-16 text-right">₹{day.payout.toFixed(0)}</span>
                  </div>
                </div>
                <span className="text-xs text-slate-500 w-14 text-right">{day.claims} claims</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-slate-400 text-sm text-center py-8">No data for the last 7 days</p>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="glass-card p-6">
          <h2 className="text-lg font-semibold text-white mb-4">Predictive Hotspots</h2>
          <div className="space-y-3">
            {(predictiveAnalytics?.hotspots || []).slice(0, 5).map((hotspot) => (
              <div key={hotspot.grid_id} className="rounded-xl bg-slate-800/60 p-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-white font-medium">{hotspot.grid_id}</p>
                    <p className="text-xs text-slate-400">{hotspot.city} · {hotspot.severity_label}</p>
                  </div>
                  <p className="text-sm font-semibold text-amber-300">₹{hotspot.expected_payout_liability.toFixed(0)}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="glass-card p-6">
          <h2 className="text-lg font-semibold text-white mb-4">City Outlook</h2>
          <div className="space-y-3">
            {(predictiveAnalytics?.cities || []).slice(0, 5).map((city) => (
              <div key={city.city} className="rounded-xl bg-slate-800/60 p-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-white font-medium">{city.city}</p>
                    <p className="text-xs text-slate-400">
                      {city.high_risk_grids} high-risk grids · {city.grid_count} monitored grids
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-semibold text-amber-300">₹{city.expected_payout_liability.toFixed(0)}</p>
                    <p className="text-xs text-slate-500">{city.expected_claims.toFixed(1)} expected claims</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="glass-card p-6">
          <h2 className="text-lg font-semibold text-white mb-4">Admin Telegram Alerts</h2>
          <p className="text-sm text-slate-400 mb-3">Link one operator chat to receive fraud spikes and disruption summaries.</p>
          <input
            value={telegramChatId}
            onChange={(e) => setTelegramChatId(e.target.value)}
            placeholder="Enter operator Telegram chat id"
            className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white"
          />
          <button onClick={handleLinkTelegram} className="mt-3 w-full rounded-xl bg-cyan-500/15 py-2 text-sm font-semibold text-cyan-300">
            Link Admin Telegram
          </button>
          {!!telegramMessage && <p className="mt-2 text-xs text-slate-400">{telegramMessage}</p>}
        </div>

        <div className="glass-card p-6">
          <h2 className="text-lg font-semibold text-white mb-4">Recent Payout Rail</h2>
          <div className="space-y-3">
            {(payoutSummary?.recent_payouts || []).slice(0, 6).map((payout) => (
              <div key={payout.id} className="rounded-xl bg-slate-800/60 p-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-white font-medium">₹{Number(payout.amount || 0).toFixed(0)}</p>
                    <p className="text-xs text-slate-400 capitalize">{String(payout.status || "").replace(/_/g, " ")}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs font-mono text-slate-300">{payout.mock_payout_id || "UPI sandbox"}</p>
                    <p className="text-xs text-slate-500">
                      {new Date(payout.created_at).toLocaleString("en-IN", {
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </p>
                  </div>
                </div>
              </div>
            ))}
            {!(payoutSummary?.recent_payouts || []).length && (
              <p className="text-sm text-slate-400">No recent payout activity yet.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
