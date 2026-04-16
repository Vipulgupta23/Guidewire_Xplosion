"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import FraudList from "@/components/admin/FraudList";

interface FlaggedClaim {
  id: string;
  trigger_type: string;
  status: string;
  payout_amount: number;
  fraud_score: number;
  fraud_flags: Array<{ type: string; layer: number; severity: string; score?: number }>;
  fraud_layer1_pass: boolean;
  fraud_layer2_pass: boolean;
  fraud_layer3_pass: boolean;
  created_at: string;
  hinglish_explanation: string;
  workers?: { name: string; platform: string; iss_score: number; grid_id: string };
}

const FLAG_DESCRIPTIONS: Record<string, string> = {
  zone_mismatch: "Worker's zone doesn't match disruption zone",
  not_recently_active: "Worker was not recently active on platform",
  duplicate_claim: "Duplicate claim for the same disruption event",
  policy_after_event: "Policy was purchased after disruption started",
  abnormal_claim_size: "Claim amount exceeds 2.2× average daily earnings",
  new_worker_high_risk: "New worker (< 14 days) — higher fraud risk",
  very_low_iss: "ISS score below 30 — unreliable worker pattern",
  ml_anomaly_detected: "Isolation Forest ML model flagged as anomalous",
};

export default function FraudPage() {
  const [flaggedClaims, setFlaggedClaims] = useState<FlaggedClaim[]>([]);
  const [actioningClaimId, setActioningClaimId] = useState<string | null>(null);
  const [pageMessage, setPageMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchFraud = async () => {
    try {
      const data = await api<FlaggedClaim[]>("/admin/fraud-list");
      setFlaggedClaims(data);
    } catch (err) {
      console.error(err);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchFraud();
    const interval = setInterval(fetchFraud, 15000);
    return () => clearInterval(interval);
  }, []);

  const handleMarkLegit = async (claimId: string) => {
    setActioningClaimId(claimId);
    setPageMessage(null);
    try {
      await api(`/claims/${claimId}/approve`, { method: "PUT" });
      setPageMessage("Claim approved successfully.");
    } catch (err) {
      setPageMessage(err instanceof Error ? err.message : "Failed to approve claim");
    } finally {
      await fetchFraud();
      setActioningClaimId(null);
    }
  };

  const handleConfirmFraud = async (claimId: string) => {
    setActioningClaimId(claimId);
    setPageMessage(null);
    try {
      await api(`/claims/${claimId}/reject`, { method: "PUT" });
      setPageMessage("Claim rejected successfully.");
    } catch (err) {
      setPageMessage(err instanceof Error ? err.message : "Failed to reject claim");
    } finally {
      await fetchFraud();
      setActioningClaimId(null);
    }
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
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Fraud Alerts</h1>
        <span className="bg-red-500/20 text-red-400 px-3 py-1 rounded-full text-sm font-bold">
          {flaggedClaims.length} Flagged
        </span>
      </div>

      {!!pageMessage && (
        <div className="glass-card p-3 text-sm text-slate-300">
          {pageMessage}
        </div>
      )}

      <FraudList
        claims={flaggedClaims}
        flagDescriptions={FLAG_DESCRIPTIONS}
        onMarkLegit={handleMarkLegit}
        onConfirmFraud={handleConfirmFraud}
        actioningClaimId={actioningClaimId}
      />
    </div>
  );
}
