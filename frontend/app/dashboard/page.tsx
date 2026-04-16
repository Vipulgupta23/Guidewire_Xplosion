"use client";
import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { api } from "@/lib/api";
import ISSGauge from "@/components/dashboard/ISSGauge";
import DisruptionBanner from "@/components/dashboard/DisruptionBanner";
import ActivePolicyCard from "@/components/dashboard/ActivePolicyCard";
import ClaimCard from "@/components/dashboard/ClaimCard";
import WhatsAppModal from "@/components/dashboard/WhatsAppModal";

const WorkerZoneMap = dynamic(() => import("@/components/dashboard/WorkerZoneMap"), {
  ssr: false,
});

interface LiveGrid {
  id: string;
  center_lat: number;
  center_lng: number;
  map_color: string;
  state_label: string;
  active_disruption_count: number;
}

interface PredictionAlert {
  title: string;
  description: string;
  confidence: number;
  predictive_risk_hours: number;
}

export default function DashboardPage() {
  const [worker, setWorker] = useState<Record<string, unknown> | null>(null);
  const [policy, setPolicy] = useState<Record<string, unknown> | null>(null);
  const [claims, setClaims] = useState<Array<Record<string, unknown>>>([]);
  const [protectionStatus, setProtectionStatus] = useState<Record<string, unknown> | null>(null);
  const [cityGrids, setCityGrids] = useState<LiveGrid[]>([]);
  const [showWhatsApp, setShowWhatsApp] = useState(false);
  const [latestPayout, setLatestPayout] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const workerId = localStorage.getItem("worker_id");
    if (!workerId) return;

    const fetchData = async () => {
      try {
        const [w, p, c, status] = await Promise.all([
          api<Record<string, unknown>>(`/workers/${workerId}`),
          api<{ policy: Record<string, unknown> | null }>(`/policies/active/${workerId}`),
          api<{ claims: Array<Record<string, unknown>> }>(`/claims/worker/${workerId}?limit=5`),
          api<Record<string, unknown>>(`/workers/${workerId}/protection-status`),
        ]);
        setWorker(w);
        setPolicy(p.policy);
        setClaims(c.claims || []);
        setProtectionStatus(status);
        const gridLiveStatus = status.grid_live_status as Record<string, unknown> | undefined;
        const workerGridId = (w.grid_id as string) || "";
        if (workerGridId && (gridLiveStatus?.feature_freshness as Record<string, unknown> | undefined)?.status === "stale") {
          try {
            await api(`/microgrids/${workerGridId}/refresh-live`, { method: "POST" });
          } catch (refreshErr) {
            console.error("Worker grid refresh failed:", refreshErr);
          }
        }
        if (typeof w.city === "string" && w.city) {
          const grids = await api<LiveGrid[]>(`/microgrids/live?city=${encodeURIComponent(w.city)}`);
          setCityGrids(grids);
        }

        // Auto-show WhatsApp modal for latest payout / review update
        const actionableClaim = (c.claims || []).find(
          (cl: Record<string, unknown>) =>
            cl.status === "paid" ||
            cl.status === "auto_approved" ||
            cl.status === "approved_after_review" ||
            cl.status === "soft_flagged" ||
            cl.status === "hard_flagged" ||
            cl.status === "manual_under_review"
        );
        if (actionableClaim) {
          setLatestPayout(actionableClaim);
          const shown = sessionStorage.getItem(`whatsapp_shown_${actionableClaim.id}`);
          if (!shown) {
            setTimeout(() => {
              setShowWhatsApp(true);
              sessionStorage.setItem(`whatsapp_shown_${actionableClaim.id}`, "1");
            }, 2000);
          }
        }
      } catch (err) {
        console.error("Dashboard fetch error:", err);
      }
      setLoading(false);
    };

    fetchData();
    const interval = setInterval(fetchData, 10000);
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        fetchData();
      }
    };
    window.addEventListener("focus", fetchData);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(interval);
      window.removeEventListener("focus", fetchData);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-10 h-10 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Welcome */}
      <div className="fade-in-up">
        <h1 className="text-2xl font-bold text-white">
          Hey {(worker?.name as string)?.split(" ")[0] || "there"}! 👋
        </h1>
        <p className="text-slate-400 text-sm mt-1">
          {new Date().toLocaleDateString("en-IN", { weekday: "long", month: "long", day: "numeric" })}
        </p>
      </div>

      {/* Disruption Banner */}
      <DisruptionBanner
        riskPercent={(protectionStatus?.banner as Record<string, unknown> | undefined)?.risk_percent as number || 0}
        title={(protectionStatus?.banner as Record<string, unknown> | undefined)?.title as string || "Protection Status"}
        description={(protectionStatus?.banner as Record<string, unknown> | undefined)?.description as string || "No active disruption in your zone"}
        earningDrop={(protectionStatus?.banner as Record<string, unknown> | undefined)?.earning_drop as string || "₹0–₹0"}
        isActive={Boolean((protectionStatus?.banner as Record<string, unknown> | undefined)?.is_active)}
        coverageActive={Boolean((protectionStatus?.banner as Record<string, unknown> | undefined)?.coverage_active)}
      />

      {/* Live Zone */}
      <div className="glass-card p-4">
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-white">Live Zone Watch</h2>
            <p className="text-sm text-slate-400">
              Your insured grid updates from live weather, AQI, and disruption automation every 10 seconds.
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <span className="rounded-full bg-cyan-500/10 px-3 py-1 text-xs font-semibold text-cyan-300">
              {String((((protectionStatus?.grid_live_status as Record<string, unknown> | undefined)?.state_label) as string) || "Monitoring")}
            </span>
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${
              ((protectionStatus?.notification_status as Record<string, unknown> | undefined)?.linked)
                ? "bg-emerald-500/10 text-emerald-300"
                : "bg-slate-700 text-slate-300"
            }`}>
              {((protectionStatus?.notification_status as Record<string, unknown> | undefined)?.linked)
                ? "Telegram alerts linked"
                : "Telegram not linked"}
            </span>
          </div>
        </div>

        <WorkerZoneMap
          grids={cityGrids}
          workerGridId={((protectionStatus?.worker as Record<string, unknown> | undefined)?.grid_id as string) || null}
        />

        <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
          <MiniMetric
            label="Grid"
            value={String(((protectionStatus?.worker as Record<string, unknown> | undefined)?.grid_id as string) || "N/A")}
          />
          <MiniMetric
            label="Rain 6h"
            value={`${Number((((protectionStatus?.grid_live_status as Record<string, unknown> | undefined)?.feature_snapshot as Record<string, unknown> | undefined)?.rain_6h as number) || 0).toFixed(1)} mm`}
          />
          <MiniMetric
            label="AQI"
            value={`${Math.round(Number((((protectionStatus?.grid_live_status as Record<string, unknown> | undefined)?.feature_snapshot as Record<string, unknown> | undefined)?.aqi as number) || 0))}`}
          />
          <MiniMetric
            label="Heat Index"
            value={`${Number((((protectionStatus?.grid_live_status as Record<string, unknown> | undefined)?.feature_snapshot as Record<string, unknown> | undefined)?.heat_index as number) || 0).toFixed(1)}°C`}
          />
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
          <MiniMetric
            label="Protected this week"
            value={`₹${Number((protectionStatus?.earnings_protected as number) || 0).toFixed(0)}`}
          />
          <MiniMetric
            label="ISS"
            value={`${Number((((protectionStatus?.worker as Record<string, unknown> | undefined)?.iss_score as number) || 0).toFixed(0))}`}
          />
          <MiniMetric
            label="Persona"
            value={String((((protectionStatus?.worker as Record<string, unknown> | undefined)?.persona as string) || "stabilizer")).replace(/^\w/, (c) => c.toUpperCase())}
          />
          <MiniMetric
            label="Payout status"
            value={String((((protectionStatus?.payout_summary as Record<string, unknown> | undefined)?.latest_status as string) || "watching")).replace(/_/g, " ")}
          />
        </div>

        <div className="mt-4 rounded-2xl bg-slate-800/50 p-4 text-sm">
          <p className="font-medium text-white">
            {String((((protectionStatus?.grid_live_status as Record<string, unknown> | undefined)?.premium_impact_label) as string) || "Premium remains stable in your current zone.")}
          </p>
          <p className="mt-2 text-slate-400">
            Trigger source: {String((protectionStatus?.disruption_origin as string) || "live monitoring").replace(/_/g, " ")}
          </p>
        </div>

        {!!(protectionStatus?.predictions as PredictionAlert[] | undefined)?.length && (
          <div className="mt-4 rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4">
            <p className="text-sm font-semibold text-amber-300">24–48h Predictive Alert</p>
            {((protectionStatus?.predictions as PredictionAlert[])[0]) && (
              <>
                <p className="mt-2 text-white font-medium">{(protectionStatus?.predictions as PredictionAlert[])[0].title}</p>
                <p className="mt-1 text-sm text-slate-300">{(protectionStatus?.predictions as PredictionAlert[])[0].description}</p>
                <p className="mt-2 text-xs text-slate-400">
                  Confidence {(protectionStatus?.predictions as PredictionAlert[])[0].confidence} · {(protectionStatus?.predictions as PredictionAlert[])[0].predictive_risk_hours}h predictive window
                </p>
              </>
            )}
          </div>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <div className="glass-card p-4">
          <p className="text-sm text-slate-400">Earnings protected</p>
          <p className="mt-1 text-2xl font-bold text-emerald-300">
            ₹{Number((protectionStatus?.earnings_protected as number) || 0).toFixed(0)}
          </p>
          <p className="mt-1 text-xs text-slate-500">Auto-calculated from paid + held disruption support this week</p>
        </div>
        <div className="glass-card p-4">
          <p className="text-sm text-slate-400">Active weekly coverage</p>
          <p className="mt-1 text-2xl font-bold text-cyan-300">
            {policy ? `${new Date(String((policy as Record<string, unknown>).end_date)).toLocaleDateString("en-IN", { month: "short", day: "numeric" })}` : "Inactive"}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {policy ? "Your current protection window is live." : "Buy a plan to activate zero-touch protection."}
          </p>
        </div>
        <div className="glass-card p-4">
          <p className="text-sm text-slate-400">Latest payout rail</p>
          <p className="mt-1 text-2xl font-bold text-amber-300">
            {String((((latestPayout?.upi_receipt as Record<string, unknown> | undefined)?.provider_ref) as string) || "UPI sandbox")}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {String((((latestPayout?.upi_receipt as Record<string, unknown> | undefined)?.status_label) as string) || "Awaiting payout activity")}
          </p>
        </div>
      </div>

      {/* ISS Gauge */}
      <ISSGauge
        score={(worker?.iss_score as number) || 50}
        consistency={50}
        regularity={50}
        zone={60}
        trust={100}
      />

      {/* Active Policy */}
      {policy ? (
        <ActivePolicyCard policy={policy as Parameters<typeof ActivePolicyCard>[0]["policy"]} />
      ) : (
        <div className="glass-card p-6 text-center">
          <p className="text-slate-400 mb-3">No active policy</p>
          <a href="/dashboard/policy" className="btn-primary inline-block">
            Choose a Plan →
          </a>
        </div>
      )}

      {/* Recent Claims */}
      <div>
        <h2 className="text-lg font-semibold text-white mb-3">Recent Claims</h2>
        {claims.length > 0 ? (
          <div className="space-y-3">
            {claims.map((claim, i) => (
              <div key={claim.id as string} style={{ animationDelay: `${i * 100}ms` }} className="fade-in-up">
                <ClaimCard claim={claim as Parameters<typeof ClaimCard>[0]["claim"]} />
              </div>
            ))}
          </div>
        ) : (
          <div className="glass-card p-6 text-center">
            <p className="text-slate-400 text-sm">No claims yet. Your coverage is active — we&apos;ll auto-protect you! 🛡️</p>
          </div>
        )}
      </div>

      {/* WhatsApp Modal */}
      {latestPayout && (
        <WhatsAppModal
          isOpen={showWhatsApp}
          onClose={() => setShowWhatsApp(false)}
          message={
            (latestPayout.hinglish_explanation as string) ||
            (
              latestPayout.status === "soft_flagged" || latestPayout.status === "hard_flagged"
                ? "Aapke zone mein disruption detect hua. Claim create ho gaya hai aur review ke liye hold par hai."
                : "Aapka payout process ho gaya hai!"
            )
          }
          amount={
            (latestPayout.paid_amount as number) ||
            (latestPayout.held_amount as number) ||
            (latestPayout.payout_amount as number) ||
            0
          }
        />
      )}
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-slate-800/40 p-3">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="mt-1 text-sm font-semibold text-white">{value}</p>
    </div>
  );
}
