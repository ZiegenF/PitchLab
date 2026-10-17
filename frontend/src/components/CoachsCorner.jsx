import { useEffect, useState } from "react";
import { api } from "../api";

const KINDS = {
  declining: { icon: "▼", label: "Needs work" },
  pitch_mix: { icon: "◆", label: "Pitch mix" },
  info: { icon: "i", label: "Context" },
  improving: { icon: "▲", label: "Trending up" },
};

// Rule-based insights from the API: what's slipping and what to do about it, plus what's working.
export default function CoachsCorner({ pitcherId, reloadKey }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api.insights(pitcherId).then((d) => !cancelled && setData(d));
    return () => {
      cancelled = true;
    };
  }, [pitcherId, reloadKey]);

  return (
    <section className="card coach">
      <h3 className="section-title">Coach's Corner</h3>
      {!data ? (
        <p className="muted small">Reviewing the tape…</p>
      ) : data.items.length === 0 ? (
        <p className="muted small">
          {data.has_recent
            ? "No big swings lately. Recent form matches the season."
            : `Insights compare the last ${data.recent_games} games to the season, so they'll appear once there are a few more games logged.`}
        </p>
      ) : (
        <ul className="insights">
          {data.items.map((item, i) => {
            const k = KINDS[item.kind];
            return (
              <li key={i} className={`insight insight-${item.kind}`}>
                <span className="insight-kind">
                  <span className="insight-icon" aria-hidden="true">{k.icon}</span> {k.label}
                </span>
                <strong className="insight-title">{item.title}</strong>
                <p className="insight-tip">
                  <span className="tip-label">Try this:</span> {item.tip}
                </p>
              </li>
            );
          })}
        </ul>
      )}
      <p className="muted small fine-print">
        Automated suggestions from the numbers, meant to start a conversation with a coach. Any
        pain or soreness should be checked by an athletic trainer.
      </p>
    </section>
  );
}
