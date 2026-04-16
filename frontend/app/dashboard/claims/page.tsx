"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import ClaimCard from "@/components/dashboard/ClaimCard";

interface EligibilityWindow {
  disruption_id: string;
  trigger_type: string;
  started_at: string;
  description: string;
}

interface ClaimResponse {
  claims: Array<Record<string, unknown>>;
  eligibility: {
    eligible_windows: EligibilityWindow[];
  };
}

export default function ClaimsPage() {
  const [claims, setClaims] = useState<Array<Record<string, unknown>>>([]);
  const [eligibility, setEligibility] = useState<EligibilityWindow[]>([]);
  const [loading, setLoading] = useState(true);
  const [submittingFallback, setSubmittingFallback] = useState<string | null>(null);

  const fetchClaims = async () => {
    const workerId = localStorage.getItem("worker_id");
    if (!workerId) return;
    try {
      const data = await api<ClaimResponse>(`/claims/worker/${workerId}?limit=20`);
      setClaims(data.claims || []);
      setEligibility(data.eligibility?.eligible_windows || []);
    } catch (err) {
      console.error(err);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchClaims();
    const interval = setInterval(fetchClaims, 10000);
    const handleFocus = () => {
      fetchClaims();
    };
    window.addEventListener("focus", handleFocus);
    return () => {
      clearInterval(interval);
      window.removeEventListener("focus", handleFocus);
    };
  }, []);

  const handleFallback = async (disruptionId: string) => {
    const workerId = localStorage.getItem("worker_id");
    if (!workerId) return;
    setSubmittingFallback(disruptionId);
    try {
      await api("/claims/fallback", {
        method: "POST",
        body: {
          worker_id: workerId,
          disruption_id: disruptionId,
        },
      });
      await fetchClaims();
    } catch (err) {
      console.error(err);
    }
    setSubmittingFallback(null);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-10 h-10 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const totalPayout = claims.reduce(
    (sum, c) => sum + ((c.paid_amount as number) || (c.payout_amount as number) || 0),
    0,
  );
  const approvedCount = claims.filter(
    (c) => c.status === "paid" || c.status === "approved_after_review",
  ).length;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-white">Claims History</h1>

      {eligibility.length > 0 && (
        <div className="glass-card p-4 border border-cyan-400/20 bg-cyan-400/5">
          <div className="mb-3">
            <p className="text-white font-semibold">Missed a disruption?</p>
            <p className="text-slate-400 text-sm">
              Zero-touch stays primary, but you can request a fallback review if automation missed a recent protected event.
            </p>
          </div>
          <div className="space-y-2">
            {eligibility.map((item) => (
              <div key={item.disruption_id} className="flex items-center justify-between gap-4 rounded-xl bg-slate-800/50 p-3">
                <div>
                  <p className="text-white text-sm font-medium capitalize">{item.trigger_type.replace(/_/g, " ")}</p>
                  <p className="text-slate-400 text-xs">
                    {new Date(item.started_at).toLocaleString("en-IN", {
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">{item.description}</p>
                </div>
                <button
                  onClick={() => handleFallback(item.disruption_id)}
                  disabled={submittingFallback === item.disruption_id}
                  className="rounded-lg bg-cyan-500/20 px-3 py-2 text-xs font-semibold text-cyan-300 hover:bg-cyan-500/30 disabled:opacity-60"
                >
                  {submittingFallback === item.disruption_id ? "Submitting..." : "Request Review"}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-3 gap-3">
        <div className="glass-card p-3 text-center">
          <p className="text-2xl font-bold text-white">{claims.length}</p>
          <p className="text-xs text-slate-400">Total Claims</p>
        </div>
        <div className="glass-card p-3 text-center">
          <p className="text-2xl font-bold text-emerald-400">{approvedCount}</p>
          <p className="text-xs text-slate-400">Resolved</p>
        </div>
        <div className="glass-card p-3 text-center">
          <p className="text-2xl font-bold text-amber-400">₹{totalPayout.toFixed(0)}</p>
          <p className="text-xs text-slate-400">Total Paid</p>
        </div>
      </div>

      {claims.length > 0 ? (
        <div className="space-y-3">
          {claims.map((claim, i) => (
            <div key={claim.id as string} style={{ animationDelay: `${i * 80}ms` }} className="fade-in-up">
              <ClaimCard claim={claim as Parameters<typeof ClaimCard>[0]["claim"]} />
            </div>
          ))}
        </div>
      ) : (
        <div className="glass-card p-8 text-center">
          <p className="text-3xl mb-3">🛡️</p>
          <p className="text-white font-semibold">No claims yet</p>
          <p className="text-slate-400 text-sm mt-1">
            We&apos;re monitoring weather and AQI 24/7. Claims are processed automatically, and fallback review is available only if we miss a real disruption.
          </p>
        </div>
      )}
    </div>
  );
}
