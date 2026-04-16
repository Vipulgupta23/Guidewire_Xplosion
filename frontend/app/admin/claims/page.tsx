"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import ClaimsTable from "@/components/admin/ClaimsTable";

interface TimelineItem {
  id: string;
  event_type: string;
  note?: string;
  created_at: string;
}

interface PayoutItem {
  id: string;
  amount: number;
  status: string;
  created_at: string;
  paid_at?: string;
}

interface Claim {
  id: string;
  trigger_type: string;
  status: string;
  payout_amount: number;
  claim_origin?: string;
  income_gap?: number;
  fraud_score: number;
  created_at: string;
  review_reason?: string;
  resolution_note?: string;
  latest_payout_status?: string;
  hinglish_explanation?: string;
  earning_simulation?: Record<string, unknown>;
  audit_trail?: {
    events?: TimelineItem[];
    payouts?: PayoutItem[];
  };
  workers?: { name: string; platform: string; grid_id: string };
}

export default function AdminClaimsPage() {
  const [claims, setClaims] = useState<Claim[]>([]);
  const [actioningClaimId, setActioningClaimId] = useState<string | null>(null);
  const [simulating, setSimulating] = useState(false);
  const [simForm, setSimForm] = useState({
    trigger_type: "heavy_rainfall",
    grid_id: "BLR_05_08",
    severity: 65,
  });
  const [simResult, setSimResult] = useState<string | null>(null);
  const [selectedClaim, setSelectedClaim] = useState<Claim | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [originFilter, setOriginFilter] = useState("all");
  const [reviewableOnly, setReviewableOnly] = useState(false);
  const [pageMessage, setPageMessage] = useState<string | null>(null);

  const fetchClaims = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: "50" });
      if (statusFilter !== "all") params.set("status", statusFilter);
      if (originFilter !== "all") params.set("claim_origin", originFilter);
      if (reviewableOnly) params.set("reviewable_only", "true");
      const data = await api<Claim[]>(`/admin/claims-queue?${params.toString()}`);
      setClaims(data);
    } catch (err) {
      console.error(err);
    }
  }, [originFilter, reviewableOnly, statusFilter]);

  useEffect(() => {
    fetchClaims();
    const interval = setInterval(fetchClaims, 10000);
    return () => clearInterval(interval);
  }, [fetchClaims]);

  const handleSimulate = async () => {
    setSimulating(true);
    setSimResult(null);
    try {
      const res = await api<{ message: string; demo_note?: string }>("/admin/simulate-trigger", {
        method: "POST",
        body: simForm,
      });
      setSimResult(res.demo_note ? `${res.message} ${res.demo_note}` : res.message);
      setTimeout(fetchClaims, 2000);
    } catch (err) {
      setSimResult(`Error: ${err instanceof Error ? err.message : "Failed"}`);
    }
    setSimulating(false);
  };

  const handleApprove = async (claimId: string) => {
    setActioningClaimId(claimId);
    setPageMessage(null);
    try {
      await api(`/claims/${claimId}/approve`, {
        method: "PUT",
        body: { reviewer: "admin_console" },
      });
      await fetchClaims();
      if (selectedClaim?.id === claimId) {
        const detail = await api<Claim>(`/claims/${claimId}`);
        setSelectedClaim(detail);
      }
      setPageMessage("Claim approved successfully.");
    } catch (err) {
      setPageMessage(err instanceof Error ? err.message : "Failed to approve claim");
      await fetchClaims();
      if (selectedClaim?.id === claimId) {
        try {
          const detail = await api<Claim>(`/claims/${claimId}`);
          setSelectedClaim(detail);
        } catch {
          setSelectedClaim(null);
        }
      }
    } finally {
      setActioningClaimId(null);
    }
  };

  const handleReject = async (claimId: string) => {
    setActioningClaimId(claimId);
    setPageMessage(null);
    try {
      await api(`/claims/${claimId}/reject`, {
        method: "PUT",
        body: { reviewer: "admin_console" },
      });
      await fetchClaims();
      if (selectedClaim?.id === claimId) {
        const detail = await api<Claim>(`/claims/${claimId}`);
        setSelectedClaim(detail);
      }
      setPageMessage("Claim rejected successfully.");
    } catch (err) {
      setPageMessage(err instanceof Error ? err.message : "Failed to reject claim");
      await fetchClaims();
      if (selectedClaim?.id === claimId) {
        try {
          const detail = await api<Claim>(`/claims/${claimId}`);
          setSelectedClaim(detail);
        } catch {
          setSelectedClaim(null);
        }
      }
    } finally {
      setActioningClaimId(null);
    }
  };

  const handleSelectClaim = async (claim: Claim) => {
    const detail = await api<Claim>(`/claims/${claim.id}`);
    setSelectedClaim(detail);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Claims Queue</h1>
        <span className="text-sm text-slate-400">Auto-refreshes every 10s</span>
      </div>

      {!!pageMessage && (
        <div className="glass-card p-3 text-sm text-slate-300">
          {pageMessage}
        </div>
      )}

      <div className="glass-card p-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="input-field text-sm">
            <option value="all">All statuses</option>
            <option value="paid">Paid</option>
            <option value="soft_flagged">Soft flagged</option>
            <option value="hard_flagged">Hard flagged</option>
            <option value="manual_under_review">Manual under review</option>
            <option value="approved_after_review">Approved after review</option>
            <option value="rejected">Rejected</option>
          </select>
          <select value={originFilter} onChange={(e) => setOriginFilter(e.target.value)} className="input-field text-sm">
            <option value="all">All origins</option>
            <option value="auto">Zero-touch only</option>
            <option value="manual">Fallback/manual only</option>
          </select>
          <label className="flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900/40 px-4 text-sm text-slate-300">
            <input type="checkbox" checked={reviewableOnly} onChange={(e) => setReviewableOnly(e.target.checked)} />
            Reviewable only
          </label>
        </div>
      </div>

      <div className="glass-card p-5 border-2 border-red-500/30">
        <div className="flex items-center gap-2 mb-4">
          <span className="text-xl">🔴</span>
          <h2 className="text-lg font-bold text-white">Simulate Disruption</h2>
          <span className="text-xs bg-red-500/20 text-red-400 px-2 py-0.5 rounded-full">DEMO</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div>
            <label className="text-xs text-slate-400 block mb-1">Trigger Type</label>
            <select
              value={simForm.trigger_type}
              onChange={(e) => setSimForm({ ...simForm, trigger_type: e.target.value })}
              className="input-field text-sm"
            >
              <option value="heavy_rainfall">🌧️ Heavy Rainfall</option>
              <option value="extreme_heat">🌡️ Extreme Heat</option>
              <option value="severe_aqi">😷 Severe AQI</option>
              <option value="flood_alert">🌊 Flood Alert</option>
              <option value="platform_outage">📵 Platform Outage (Demo only)</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-400 block mb-1">Grid ID</label>
            <input
              value={simForm.grid_id}
              onChange={(e) => setSimForm({ ...simForm, grid_id: e.target.value })}
              className="input-field text-sm"
              placeholder="BLR_05_08"
            />
          </div>
          <div>
            <label className="text-xs text-slate-400 block mb-1">Severity</label>
            <input
              type="number"
              value={simForm.severity}
              onChange={(e) => setSimForm({ ...simForm, severity: Number(e.target.value) })}
              className="input-field text-sm"
            />
          </div>
          <div className="flex items-end">
            <button
              onClick={handleSimulate}
              disabled={simulating}
              className="w-full bg-red-500 hover:bg-red-600 text-white font-bold py-3 px-4 rounded-xl transition-all active:scale-95 disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {simulating ? (
                <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              ) : (
                <>🔴 Fire Trigger</>
              )}
            </button>
          </div>
        </div>

        {simResult && (
          <div className="mt-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl p-3 text-sm text-emerald-400">
            {simResult}
          </div>
        )}

        <p className="mt-3 text-xs text-slate-400">
          `platform_outage` is intentionally admin-simulated for the Phase 2 demo and is not scheduler auto-detected.
        </p>
      </div>

      <ClaimsTable
        claims={claims}
        onSelectClaim={handleSelectClaim}
        onApprove={handleApprove}
        onReject={handleReject}
        actioningClaimId={actioningClaimId}
      />

      {selectedClaim && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={() => setSelectedClaim(null)}>
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
          <div className="relative w-full max-w-2xl mx-4 glass-card p-6 max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-white">Claim Details</h3>
              <button onClick={() => setSelectedClaim(null)} className="text-slate-400 hover:text-white text-xl">✕</button>
            </div>

            <div className="space-y-4 text-sm">
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-xl bg-slate-800/60 p-3">
                  <p className="text-slate-400 text-xs">Worker</p>
                  <p className="text-white">{selectedClaim.workers?.name}</p>
                </div>
                <div className="rounded-xl bg-slate-800/60 p-3">
                  <p className="text-slate-400 text-xs">Origin</p>
                  <p className="text-white capitalize">{(selectedClaim.claim_origin || "auto").replace(/_/g, " ")}</p>
                </div>
                <div className="rounded-xl bg-slate-800/60 p-3">
                  <p className="text-slate-400 text-xs">Income Gap</p>
                  <p className="text-red-400">₹{(selectedClaim.income_gap ?? 0).toFixed(0)}</p>
                </div>
                <div className="rounded-xl bg-slate-800/60 p-3">
                  <p className="text-slate-400 text-xs">Payout</p>
                  <p className="text-emerald-400 font-bold">₹{selectedClaim.payout_amount.toFixed(0)}</p>
                </div>
                <div className="rounded-xl bg-slate-800/60 p-3">
                  <p className="text-slate-400 text-xs">Fraud Score</p>
                  <p className={selectedClaim.fraud_score > 0.5 ? "text-red-400" : "text-emerald-400"}>
                    {(selectedClaim.fraud_score * 100).toFixed(0)}%
                  </p>
                </div>
                <div className="rounded-xl bg-slate-800/60 p-3">
                  <p className="text-slate-400 text-xs">Payout State</p>
                  <p className="text-white capitalize">{(selectedClaim.latest_payout_status || "n/a").replace(/_/g, " ")}</p>
                </div>
              </div>

              <div>
                <p className="text-slate-400 mb-1">Hinglish Explanation</p>
                <p className="text-emerald-300 bg-emerald-500/10 p-3 rounded-xl text-sm">
                  {selectedClaim.hinglish_explanation || "Explanation will appear after claim processing."}
                </p>
              </div>

              {(selectedClaim.review_reason || selectedClaim.resolution_note) && (
                <div>
                  <p className="text-slate-400 mb-1">Resolution</p>
                  <p className="text-slate-300 bg-slate-800/60 p-3 rounded-xl text-sm">
                    Reason: {(selectedClaim.review_reason || "operator_review").replace(/_/g, " ")}
                    {selectedClaim.resolution_note ? ` · ${selectedClaim.resolution_note}` : ""}
                  </p>
                </div>
              )}

              {!!selectedClaim.audit_trail?.payouts?.length && (
                <div>
                  <p className="text-slate-400 mb-1">Payout Timeline</p>
                  <div className="space-y-2">
                    {selectedClaim.audit_trail.payouts.map((payout) => (
                      <div key={payout.id} className="rounded-xl bg-slate-800/60 p-3 text-sm">
                        <div className="flex justify-between">
                          <span className="text-white">₹{payout.amount.toFixed(0)}</span>
                          <span className="text-slate-300 capitalize">{payout.status.replace(/_/g, " ")}</span>
                        </div>
                        <p className="mt-1 text-xs text-slate-500">
                          {new Date(payout.paid_at || payout.created_at).toLocaleString("en-IN", {
                            month: "short",
                            day: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {!!selectedClaim.audit_trail?.events?.length && (
                <div>
                  <p className="text-slate-400 mb-1">Claim Event Timeline</p>
                  <div className="space-y-2">
                    {selectedClaim.audit_trail.events.map((event) => (
                      <div key={event.id} className="rounded-xl bg-slate-800/60 p-3 text-sm">
                        <div className="flex justify-between gap-4">
                          <span className="text-white capitalize">{event.event_type.replace(/_/g, " ")}</span>
                          <span className="text-slate-500 text-xs">
                            {new Date(event.created_at).toLocaleString("en-IN", {
                              month: "short",
                              day: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </span>
                        </div>
                        {event.note && <p className="mt-1 text-slate-400 text-xs">{event.note}</p>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
