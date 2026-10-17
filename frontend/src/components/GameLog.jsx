import { useState } from "react";

const COLS = ["innings_pitched", "hits", "runs", "earned_runs", "walks", "strikeouts", "home_runs", "pitches"];
const LABELS = ["IP", "H", "R", "ER", "BB", "K", "HR", "Pitches"];

// A box score, one row per outing. Rows with pitch data can be clicked to plot that game.
export default function GameLog({ games, selectedId, onSelect, onDelete, canEdit }) {
  const [confirmId, setConfirmId] = useState(null);

  if (!games.length) return <p className="muted small">No games yet.</p>;

  return (
    <div className="table-scroll game-log">
      <table className="data-table box-score">
        <thead>
          <tr>
            <th className="left">Date</th>
            <th className="left">Opp</th>
            <th className="left">GS</th>
            {LABELS.map((l) => (
              <th key={l}>{l}</th>
            ))}
            {canEdit && <th aria-label="Actions" />}
          </tr>
        </thead>
        <tbody>
          {games.map((g) => (
            <tr
              key={g.id}
              className={[g.pitches ? "clickable" : "", g.id === selectedId ? "selected" : ""].join(" ")}
              onClick={() => g.pitches && onSelect(g)}
              tabIndex={g.pitches ? 0 : undefined}
              onKeyDown={(e) => e.key === "Enter" && g.pitches && onSelect(g)}
            >
              <td className="left">{g.game_date}</td>
              <td className="left">{g.opponent}</td>
              <td className="left">{g.is_start ? "✓" : ""}</td>
              {COLS.map((c) => (
                <td key={c}>{c === "pitches" && !g.pitches ? "—" : g[c]}</td>
              ))}
              {canEdit && (
                <td onClick={(e) => e.stopPropagation()}>
                  {confirmId === g.id ? (
                    <span className="row-confirm">
                      <button className="link danger-text" onClick={() => onDelete(g)}>
                        Delete
                      </button>
                      <button className="link" onClick={() => setConfirmId(null)}>
                        Keep
                      </button>
                    </span>
                  ) : (
                    <button
                      className="icon-btn"
                      onClick={() => setConfirmId(g.id)}
                      aria-label={`Delete game on ${g.game_date}`}
                      title="Delete game"
                    >
                      ×
                    </button>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
