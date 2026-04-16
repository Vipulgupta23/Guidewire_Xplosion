interface FraudFlag {
  type: string;
  layer: number;
  severity: string;
  score?: number;
}

interface FlaggedClaim {
  id: string;
  trigger_type: string;
  status: string;
  payout_amount: number;
  fraud_score: number;
  fraud_flags: FraudFlag[];
  fraud_layer1_pass: boolean;
  fraud_layer2_pass: boolean;
  fraud_layer3_pass: boolean;
  workers?: { name: string; platform: string; iss_score: number; grid_id: string };
}

interface FraudListProps {
  claims: FlaggedClaim[];
  flagDescriptions: Record<string, string>;
  onMarkLegit: (claimId: string) => void;
  onConfirmFraud: (claimId: string) => void;
  actioningClaimId?: string | null;
}

export default function FraudList({ claims, flagDescriptions, onMarkLegit, onConfirmFraud, actioningClaimId = null }: FraudListProps) {
  if (claims.length === 0) {
    return (
      <div className="glass-card p-12 text-center">
        <p className="text-4xl mb-3">✅</p>
        <p className="text-white font-semibold text-lg">All Clear!</p>
        <p className="text-slate-400 text-sm mt-1">No fraud alerts pending review</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {claims.map((claim, i) => (
        <div
          key={claim.id}
          className={`glass-card overflow-hidden fade-in-up ${
            claim.status === "hard_flagged" ? "border-l-4 border-l-red-500" : "border-l-4 border-l-yellow-500"
          }`}
          style={{ animationDelay: `${i * 80}ms` }}
        >
          <div className="p-5">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div
                  className={`w-10 h-10 rounded-xl flex items-center justify-center text-xl ${
                    claim.status === "hard_flagged" ? "bg-red-500/20" : "bg-yellow-500/20"
                  }`}
                >
                  {claim.status === "hard_flagged" ? "🚨" : "⚠️"}
                </div>
                <div>
                  <p className="text-white font-semibold">{claim.workers?.name || "Unknown"}</p>
                  <p className="text-slate-400 text-xs capitalize">
                    {claim.workers?.platform} | ISS: {claim.workers?.iss_score?.toFixed(0)} | {claim.workers?.grid_id}
                  </p>
                </div>
              </div>
              <span className={`status-badge status-${claim.status}`}>{claim.status.replace("_", " ")}</span>
            </div>

            <div className="grid grid-cols-3 gap-2 mb-4">
              {[
                { label: "Layer 1 (Rules)", pass: claim.fraud_layer1_pass },
                { label: "Layer 2 (Behavioral)", pass: claim.fraud_layer2_pass },
                { label: "Layer 3 (ML)", pass: claim.fraud_layer3_pass },
              ].map((layer) => (
                <div
                  key={layer.label}
                  className={`text-center p-2 rounded-lg text-xs ${
                    layer.pass ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"
                  }`}
                >
                  <p className="font-bold">{layer.pass ? "PASS" : "FAIL"}</p>
                  <p className="text-slate-400 mt-0.5">{layer.label}</p>
                </div>
              ))}
            </div>

            <div className="space-y-2 mb-4">
              <p className="text-xs text-slate-400 uppercase tracking-wider">Flags Detected</p>
              {(claim.fraud_flags || []).map((flag, j) => (
                <div key={`${flag.type}-${j}`} className="flex items-start gap-2 bg-slate-800/50 p-2.5 rounded-lg">
                  <span
                    className={`text-xs px-1.5 py-0.5 rounded font-bold ${
                      flag.severity === "hard" ? "bg-red-500/20 text-red-400" : "bg-yellow-500/20 text-yellow-400"
                    }`}
                  >
                    L{flag.layer}
                  </span>
                  <div>
                    <p className="text-white text-xs font-medium capitalize">{flag.type.replace(/_/g, " ")}</p>
                    <p className="text-slate-400 text-xs mt-0.5">{flagDescriptions[flag.type] || "Unknown flag"}</p>
                    {flag.score !== undefined && <p className="text-xs text-slate-500 mt-0.5">Anomaly score: {flag.score.toFixed(4)}</p>}
                  </div>
                </div>
              ))}
            </div>

            <div className="flex items-center justify-between bg-slate-800/30 rounded-lg p-3 mb-4">
              <span className="text-slate-400 text-sm">Payout Amount</span>
              <span className="text-amber-400 font-bold text-lg">Rs {claim.payout_amount.toFixed(0)}</span>
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => onMarkLegit(claim.id)}
                disabled={actioningClaimId === claim.id}
                className="flex-1 bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 py-2.5 rounded-xl text-sm font-semibold hover:bg-emerald-500/30 transition-colors"
              >
                {actioningClaimId === claim.id ? "Processing..." : "Mark as Legitimate"}
              </button>
              <button
                onClick={() => onConfirmFraud(claim.id)}
                disabled={actioningClaimId === claim.id}
                className="flex-1 bg-red-500/20 text-red-400 border border-red-500/30 py-2.5 rounded-xl text-sm font-semibold hover:bg-red-500/30 transition-colors"
              >
                {actioningClaimId === claim.id ? "Processing..." : "Confirm Fraud"}
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
