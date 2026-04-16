"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import ISSGauge from "@/components/dashboard/ISSGauge";

export default function ProfilePage() {
  const [worker, setWorker] = useState<Record<string, unknown> | null>(null);
  const [issHistory, setIssHistory] = useState<Array<Record<string, unknown>>>([]);
  const [issBreakdown, setIssBreakdown] = useState<Record<string, unknown> | null>(null);
  const [telegramChatId, setTelegramChatId] = useState("");
  const [telegramStatus, setTelegramStatus] = useState<Record<string, unknown> | null>(null);
  const [linkMessage, setLinkMessage] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      const workerId = localStorage.getItem("worker_id");
      if (!workerId) return;
      try {
        const [w, iss] = await Promise.all([
          api<Record<string, unknown>>(`/workers/${workerId}`),
          api<Array<Record<string, unknown>>>(`/workers/${workerId}/iss-history`),
        ]);
        setWorker(w);
        setIssHistory(iss);
        const [breakdown, notifStatus] = await Promise.all([
          api<Record<string, unknown>>(`/workers/${workerId}/iss-breakdown`),
          api<Record<string, unknown>>(`/notifications/telegram/status/worker/${workerId}`),
        ]);
        setIssBreakdown(breakdown);
        setTelegramStatus(notifStatus);
        const savedChatId =
          (notifStatus?.target_id as string | undefined) ||
          localStorage.getItem(`telegram_chat_worker_${workerId}`) ||
          "";
        setTelegramChatId(savedChatId);
      } catch (err) {
        console.error(err);
      }
      setLoading(false);
    };
    fetchData();
  }, []);

  const handleLogout = () => {
    localStorage.clear();
    sessionStorage.clear();
    window.location.href = "/login";
  };

  const handleLinkTelegram = async () => {
    if (!worker || !telegramChatId) return;
    try {
      const result = await api<{ status: Record<string, unknown> }>("/notifications/telegram/link", {
        method: "POST",
        body: {
          entity_type: "worker",
          entity_id: worker.id,
          chat_id: telegramChatId,
          username: worker.name,
        },
      });
      setTelegramStatus(result.status);
      const workerId = String(worker.id);
      localStorage.setItem(`telegram_chat_worker_${workerId}`, telegramChatId);
      setLinkMessage("Telegram linked successfully");
    } catch (err) {
      setLinkMessage(err instanceof Error ? err.message : "Failed to link Telegram");
    }
  };

  const handleTestTelegram = async () => {
    if (!worker) return;
    try {
      await api("/notifications/telegram/test", {
        method: "POST",
        body: {
          entity_type: "worker",
          entity_id: worker.id,
          message: "Incometrix AI test alert: your worker notifications are live.",
        },
      });
      setLinkMessage("Telegram test message sent");
    } catch (err) {
      setLinkMessage(err instanceof Error ? err.message : "Failed to send test");
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center h-64">
      <div className="w-10 h-10 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
    </div>;
  }

  if (!worker) return null;

  const personaEmoji: Record<string, string> = { hustler: "🔥", stabilizer: "🎯", opportunist: "⚡" };

  return (
    <div className="space-y-4">
      {/* Profile Card */}
      <div className="glass-card p-6">
        <div className="flex items-center gap-4 mb-4">
          <div className="w-16 h-16 bg-gradient-to-br from-amber-400 to-amber-600 rounded-2xl flex items-center justify-center text-2xl font-bold text-slate-900">
            {(worker.name as string)?.charAt(0) || "?"}
          </div>
          <div>
            <h2 className="text-xl font-bold text-white">{worker.name as string}</h2>
            <p className="text-slate-400 text-sm capitalize">{worker.platform as string} Partner</p>
            <div className="flex items-center gap-2 mt-1">
              {worker.is_verified ? (
                <span className="text-xs bg-emerald-500/20 text-emerald-400 px-2 py-0.5 rounded-full">✅ Verified</span>
              ) : (
                <span className="text-xs bg-red-500/20 text-red-400 px-2 py-0.5 rounded-full">Unverified</span>
              )}
              <span className="text-xs bg-slate-600/50 text-slate-300 px-2 py-0.5 rounded-full capitalize">
                {personaEmoji[(worker.persona as string) || "stabilizer"]} {worker.persona as string}
              </span>
            </div>
          </div>
        </div>

        {/* Stats grid */}
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-slate-800/50 rounded-xl p-3">
            <p className="text-xs text-slate-400">Avg Daily</p>
            <p className="text-lg font-bold text-white">₹{(worker.avg_daily_earnings as number)?.toFixed(0) || "900"}</p>
          </div>
          <div className="bg-slate-800/50 rounded-xl p-3">
            <p className="text-xs text-slate-400">Active Days/Week</p>
            <p className="text-lg font-bold text-white">{(worker.active_days_per_week as number)?.toFixed(1) || "5.0"}</p>
          </div>
          <div className="bg-slate-800/50 rounded-xl p-3">
            <p className="text-xs text-slate-400">Grid Zone</p>
            <p className="text-lg font-bold text-white">{worker.grid_id as string || "BLR_05_08"}</p>
          </div>
          <div className="bg-slate-800/50 rounded-xl p-3">
            <p className="text-xs text-slate-400">Peak Hour Ratio</p>
            <p className="text-lg font-bold text-white">{((worker.peak_hour_ratio as number) * 100)?.toFixed(0) || "50"}%</p>
          </div>
        </div>
      </div>

      {/* ISS Gauge */}
      <ISSGauge
        score={(worker.iss_score as number) || 50}
        consistency={issHistory[0]?.consistency_score as number || 50}
        regularity={issHistory[0]?.regularity_score as number || 50}
        zone={issHistory[0]?.zone_score as number || 60}
        trust={issHistory[0]?.fraud_score_component as number || 100}
      />

      {issBreakdown && (
        <div className="glass-card p-4">
          <h3 className="text-sm font-semibold text-white mb-3">ISS Impact Summary</h3>
          <p className="text-sm text-slate-300">{issBreakdown.impact_summary as string}</p>
        </div>
      )}

      <div className="glass-card p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-white">Telegram Alerts</h3>
            <p className="text-xs text-slate-400">Link your Telegram chat to receive disruption and payout updates.</p>
          </div>
          <span className={`text-xs rounded-full px-2 py-1 ${
            telegramStatus?.linked ? "bg-emerald-500/20 text-emerald-300" : "bg-slate-700 text-slate-300"
          }`}>
            {telegramStatus?.linked ? "Linked" : "Not linked"}
          </span>
        </div>
        <input
          value={telegramChatId}
          onChange={(e) => setTelegramChatId(e.target.value)}
          placeholder="Enter your Telegram chat id"
          className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white"
        />
        <div className="flex gap-2">
          <button onClick={handleLinkTelegram} className="flex-1 rounded-xl bg-cyan-500/15 py-2 text-sm font-semibold text-cyan-300">
            Link Telegram
          </button>
          <button onClick={handleTestTelegram} className="flex-1 rounded-xl bg-amber-500/15 py-2 text-sm font-semibold text-amber-300">
            Send Test
          </button>
        </div>
        {!!linkMessage && <p className="text-xs text-slate-400">{linkMessage}</p>}
      </div>

      {/* ISS History */}
      {issHistory.length > 1 && (
        <div className="glass-card p-4">
          <h3 className="text-sm font-semibold text-white mb-3">ISS History</h3>
          <div className="space-y-2">
            {issHistory.slice(0, 10).map((entry, i) => (
              <div key={entry.id as string || i} className="flex items-center justify-between text-sm">
                <span className="text-slate-400">
                  {new Date(entry.calculated_at as string).toLocaleDateString("en-IN", { month: "short", day: "numeric" })}
                </span>
                <div className="flex items-center gap-2">
                  <span className={`font-bold ${
                    (entry.iss_score as number) >= 70 ? "text-emerald-400" :
                    (entry.iss_score as number) >= 45 ? "text-amber-400" : "text-red-400"
                  }`}>
                    {(entry.iss_score as number)?.toFixed(1)}
                  </span>
                  {(entry.delta as number) !== 0 && (
                    <span className={`text-xs ${(entry.delta as number) > 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {(entry.delta as number) > 0 ? "+" : ""}{(entry.delta as number)?.toFixed(1)}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Logout */}
      <button
        onClick={handleLogout}
        className="w-full bg-red-500/10 text-red-400 border border-red-500/30 py-3 rounded-xl font-medium hover:bg-red-500/20 transition-colors"
      >
        Logout
      </button>
    </div>
  );
}
