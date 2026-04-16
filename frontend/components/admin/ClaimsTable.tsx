interface Claim {
  id: string;
  trigger_type: string;
  status: string;
  payout_amount: number;
  claim_origin?: string;
  fraud_score: number;
  created_at: string;
  workers?: { name: string; platform: string; grid_id: string };
}

interface ClaimsTableProps {
  claims: Claim[];
  onSelectClaim: (claim: Claim) => void;
  onApprove: (claimId: string) => void;
  onReject: (claimId: string) => void;
  actioningClaimId?: string | null;
}

const TRIGGER_ICONS: Record<string, string> = {
  heavy_rainfall: "🌧️",
  extreme_heat: "🌡️",
  severe_aqi: "😷",
  flood_alert: "🌊",
  platform_outage: "📵",
  cyclone: "🌪️",
};

export default function ClaimsTable({ claims, onSelectClaim, onApprove, onReject, actioningClaimId = null }: ClaimsTableProps) {
  return (
    <div className="glass-card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700 text-left">
              <th className="px-4 py-3 text-slate-400 font-medium">Worker</th>
              <th className="px-4 py-3 text-slate-400 font-medium">Trigger</th>
              <th className="px-4 py-3 text-slate-400 font-medium text-right">Payout</th>
              <th className="px-4 py-3 text-slate-400 font-medium text-center">Status</th>
              <th className="px-4 py-3 text-slate-400 font-medium text-center">Fraud</th>
              <th className="px-4 py-3 text-slate-400 font-medium">Time</th>
              <th className="px-4 py-3 text-slate-400 font-medium text-center">Actions</th>
            </tr>
          </thead>
          <tbody>
            {claims.map((claim, i) => (
              <tr
                key={claim.id}
                className={`border-b border-slate-800 hover:bg-slate-800/50 cursor-pointer transition-colors ${
                  claim.status === "hard_flagged" ? "bg-red-500/5" : claim.status === "soft_flagged" ? "bg-yellow-500/5" : ""
                }`}
                onClick={() => onSelectClaim(claim)}
                style={{ animationDelay: `${i * 30}ms` }}
              >
                <td className="px-4 py-3">
                  <p className="text-white font-medium">{claim.workers?.name || "Worker"}</p>
                  <p className="text-slate-500 text-xs capitalize">
                    {claim.workers?.platform} · {(claim.claim_origin || "auto").replace(/_/g, " ")}
                  </p>
                </td>
                <td className="px-4 py-3">
                  <span className="flex items-center gap-1.5">
                    {TRIGGER_ICONS[claim.trigger_type] || "⚡"}
                    <span className="text-slate-300 capitalize">{claim.trigger_type.replace(/_/g, " ")}</span>
                  </span>
                </td>
                <td className="px-4 py-3 text-right font-bold text-emerald-400">Rs {claim.payout_amount.toFixed(0)}</td>
                <td className="px-4 py-3 text-center">
                  <span className={`status-badge status-${claim.status}`}>
                    {claim.status === "approved_after_review" ? "approved after review" : claim.status.replace("_", " ")}
                  </span>
                </td>
                <td className="px-4 py-3 text-center">
                  <span
                    className={`text-xs font-mono ${
                      claim.fraud_score > 0.5 ? "text-red-400" : claim.fraud_score > 0.25 ? "text-yellow-400" : "text-emerald-400"
                    }`}
                  >
                    {(claim.fraud_score * 100).toFixed(0)}%
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-400 text-xs">
                  {new Date(claim.created_at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
                </td>
                <td className="px-4 py-3 text-center" onClick={(e) => e.stopPropagation()}>
                  {(claim.status === "soft_flagged" || claim.status === "hard_flagged" || claim.status === "manual_under_review" || claim.status === "manual_submitted") && (
                    <div className="flex gap-1 justify-center">
                      <button
                        onClick={() => onApprove(claim.id)}
                        disabled={actioningClaimId === claim.id}
                        className="text-xs bg-emerald-500/20 text-emerald-400 px-2.5 py-1 rounded-lg hover:bg-emerald-500/30"
                      >
                        {actioningClaimId === claim.id ? "..." : "✓"}
                      </button>
                      <button
                        onClick={() => onReject(claim.id)}
                        disabled={actioningClaimId === claim.id}
                        className="text-xs bg-red-500/20 text-red-400 px-2.5 py-1 rounded-lg hover:bg-red-500/30"
                      >
                        {actioningClaimId === claim.id ? "..." : "✕"}
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {claims.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-slate-400">
                  No claims yet. Use &quot;Simulate Disruption&quot; above to create some!
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
