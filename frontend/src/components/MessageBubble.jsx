function riskColor(score) {
  if (score >= 0.6) return "var(--danger)";
  if (score >= 0.3) return "var(--warn)";
  return "var(--accent)";
}

export default function MessageBubble({ message }) {
  const { role, content, guard } = message;

  if (message.blocked) {
    return (
      <div className="bubble-row user">
        <div className="blocked-banner">
          Blocked — risk score {guard.risk_score.toFixed(2)}
          <div className="reasons">
            {guard.reasons.length > 0
              ? guard.reasons.slice(0, 3).join(" · ")
              : "Pattern-based heuristics flagged this input."}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`bubble-row ${role}`}>
      <div className="bubble">{content}</div>
      {role === "user" && guard && (
        <div className="guard-strip">
          <div className="risk-meter">
            <div
              className="risk-meter-fill"
              style={{
                width: `${Math.round(guard.risk_score * 100)}%`,
                backgroundColor: riskColor(guard.risk_score),
              }}
            />
          </div>
          <span>risk {guard.risk_score.toFixed(2)}</span>
        </div>
      )}
    </div>
  );
}
