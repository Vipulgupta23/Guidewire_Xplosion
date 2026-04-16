"use client";
import { useState } from "react";
import EarningSimTable from "@/components/dashboard/EarningSimTable";

interface ClaimEvent {
  id: string;
  event_type: string;
  note?: string;
  created_at: string;
}

interface ClaimCardProps {
  claim: {
    id: string;
    trigger_type: string;
    status: string;
    payout_amount: number;
    paid_amount?: number;
    held_amount?: number;
    recommended_payout?: number;
    income_gap: number;
    simulated_earnings: number;
    actual_earnings: number;
    coverage_pct: number;
    fraud_score: number;
    hinglish_explanation: string;
    claim_origin?: string;
    review_reason?: string;
    resolution_note?: string;
    latest_payout_status?: string;
    upi_receipt?: {
      provider_ref?: string;
      status_label?: string;
    };
    fraud_report?: {
      operator_summary?: string;
      risk_level?: string;
      delivery_specific_flags?: Array<{
        type: string;
        distance_km?: number;
      }>;
    };
    claim_events?: ClaimEvent[];
    earning_simulation?: {
      hourly_breakdown: Array<{
        hour_label: string;
        is_peak: boolean;
        deliveries_expected: number;
        earnings_expected: number;
        deliveries_actual: number;
        earnings_actual: number;
        disrupted: boolean;
        surge_label: string;
      }>;
    };
    created_at: string;
  };
}

const TRIGGER_ICONS: Record<string, string> = {
  heavy_rainfall: "🌧️",
  extreme_heat: "🌡️",
  severe_aqi: "😷",
  flood_alert: "🌊",
  platform_outage: "📵",
  cyclone: "🌪️",
};

const CLAIM_STATUS_LABELS: Record<string, string> = {
  processing: "Auto-processing",
  auto_approved: "Auto-approved",
  paid: "Paid",
  soft_flagged: "Flagged for review",
  hard_flagged: "Blocked for review",
  manual_submitted: "Fallback submitted",
  manual_under_review: "Fallback under review",
  approved_after_review: "Approved after review",
  rejected: "Rejected",
};

const CLAIM_STATUS_DESCRIPTIONS: Record<string, string> = {
  processing: "We are validating the disruption and payout details.",
  auto_approved: "Your claim passed automation checks and is moving to payout.",
  paid: "Your zero-touch payout was sent successfully.",
  soft_flagged: "A partial hold or behavior check requires admin review.",
  hard_flagged: "The payout is blocked until an operator reviews it.",
  manual_submitted: "Your fallback request was submitted successfully.",
  manual_under_review: "An operator is reviewing this fallback claim.",
  approved_after_review: "An operator approved this claim after review.",
  rejected: "This claim failed review and no payout will be issued.",
};

export default function ClaimCard({ claim }: ClaimCardProps) {
  const [showExplanation, setShowExplanation] = useState(false);
  const [showSimulation, setShowSimulation] = useState(false);
  const [showTimeline, setShowTimeline] = useState(false);

  const icon = TRIGGER_ICONS[claim.trigger_type] || "⚡";
  const date = new Date(claim.created_at).toLocaleDateString("en-IN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className="glass-card p-4">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-slate-700 rounded-xl flex items-center justify-center text-xl">
            {icon}
          </div>
          <div>
            <p className="text-white font-semibold text-sm capitalize">
              {claim.trigger_type.replace(/_/g, " ")}
            </p>
            <p className="text-slate-400 text-xs">{date}</p>
            <p className="text-slate-500 text-[11px] capitalize">
              {claim.claim_origin === "manual" ? "Fallback review claim" : "Zero-touch claim"}
            </p>
          </div>
        </div>
        <span className={`status-badge status-${claim.status}`}>
          {CLAIM_STATUS_LABELS[claim.status] || claim.status.replace("_", " ")}
        </span>
      </div>

      <div className="bg-slate-800/60 rounded-xl p-3 mb-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400">Income Gap</p>
            <p className="text-red-400 font-semibold">₹{claim.income_gap.toFixed(0)}</p>
          </div>
          <div className="text-center">
            <p className="text-xs text-slate-400">Coverage</p>
            <p className="text-slate-300 font-medium">{((claim.coverage_pct || 0.7) * 100).toFixed(0)}%</p>
          </div>
          <div className="text-right">
            <p className="text-xs text-slate-400">Payout</p>
            <p className="text-emerald-400 font-bold text-lg">₹{(claim.paid_amount ?? claim.payout_amount).toFixed(0)}</p>
            {claim.recommended_payout !== undefined &&
              claim.recommended_payout !== (claim.paid_amount ?? claim.payout_amount) && (
                <p className="text-[11px] text-slate-500">Eligible ₹{claim.recommended_payout.toFixed(0)}</p>
              )}
          </div>
        </div>
      </div>

      <p className="text-xs text-slate-400 mb-3">
        {CLAIM_STATUS_DESCRIPTIONS[claim.status] || "Claim processed by the zero-touch engine."}
      </p>

      {(claim.latest_payout_status || claim.review_reason) && (
        <div className="mb-3 rounded-lg bg-slate-800/40 p-3 text-xs text-slate-300">
          {claim.latest_payout_status && (
            <p>
              Payout status: <span className="capitalize text-white">{claim.latest_payout_status.replace(/_/g, " ")}</span>
            </p>
          )}
          {claim.review_reason && (
            <p className="mt-1">
              Review reason: <span className="text-white">{claim.review_reason.replace(/_/g, " ")}</span>
            </p>
          )}
          {claim.resolution_note && <p className="mt-1 text-slate-400">{claim.resolution_note}</p>}
          {claim.upi_receipt?.provider_ref && (
            <p className="mt-1">
              UPI ref: <span className="text-white">{claim.upi_receipt.provider_ref}</span>
            </p>
          )}
          {claim.upi_receipt?.status_label && (
            <p className="mt-1 text-slate-400">{claim.upi_receipt.status_label}</p>
          )}
        </div>
      )}

      {claim.fraud_report?.operator_summary && (
        <div className="mb-3 rounded-lg bg-slate-800/30 p-3 text-xs text-slate-400">
          {claim.fraud_report?.risk_level && (
            <p className="mb-1 text-slate-300">
              Fraud risk: <span className="capitalize text-white">{claim.fraud_report.risk_level}</span>
            </p>
          )}
          {claim.fraud_report.operator_summary}
          {!!claim.fraud_report?.delivery_specific_flags?.length && (
            <div className="mt-2 space-y-1">
              {claim.fraud_report.delivery_specific_flags.map((flag) => (
                <p key={flag.type} className="text-[11px] text-amber-300">
                  {flag.type.replace(/_/g, " ")}
                  {typeof flag.distance_km === "number" ? ` · ${flag.distance_km.toFixed(1)} km mismatch` : ""}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => setShowExplanation(!showExplanation)}
          className="flex-1 min-w-[110px] text-sm bg-amber-500/10 text-amber-400 py-2 px-3 rounded-lg hover:bg-amber-500/20 transition-colors font-medium"
        >
          Why? 🤖
        </button>
        <button
          onClick={() => setShowSimulation(!showSimulation)}
          className="flex-1 min-w-[110px] text-sm bg-blue-500/10 text-blue-400 py-2 px-3 rounded-lg hover:bg-blue-500/20 transition-colors font-medium"
        >
          Simulation 📊
        </button>
        <button
          onClick={() => setShowTimeline(!showTimeline)}
          className="flex-1 min-w-[110px] text-sm bg-cyan-500/10 text-cyan-400 py-2 px-3 rounded-lg hover:bg-cyan-500/20 transition-colors font-medium"
        >
          Timeline 🕒
        </button>
      </div>

      {showExplanation && (
        <div className="mt-3 bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-4 fade-in-up">
          <p className="text-emerald-300 text-sm leading-relaxed">{claim.hinglish_explanation}</p>
        </div>
      )}

      {showSimulation && claim.earning_simulation?.hourly_breakdown && (
        <div className="mt-3 fade-in-up">
          <EarningSimTable
            rows={claim.earning_simulation.hourly_breakdown}
            simulatedEarnings={claim.simulated_earnings}
            actualEarnings={claim.actual_earnings}
            payoutAmount={claim.payout_amount}
          />
        </div>
      )}

      {showTimeline && (claim.claim_events || []).length > 0 && (
        <div className="mt-3 rounded-xl bg-slate-800/50 p-4 fade-in-up">
          <p className="mb-3 text-xs uppercase tracking-wider text-slate-400">Claim Timeline</p>
          <div className="space-y-2">
            {(claim.claim_events || []).map((event) => (
              <div key={event.id} className="flex items-start justify-between gap-4 rounded-lg border border-slate-700/60 p-2">
                <div>
                  <p className="text-sm text-white capitalize">{event.event_type.replace(/_/g, " ")}</p>
                  {event.note && <p className="text-xs text-slate-400 mt-0.5">{event.note}</p>}
                </div>
                <p className="text-[11px] text-slate-500">
                  {new Date(event.created_at).toLocaleString("en-IN", {
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
    </div>
  );
}
