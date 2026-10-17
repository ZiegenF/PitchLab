import { useState } from "react";
import { useAuth, useTilePrefs } from "../auth";
import { formatStat } from "../stats";
import StatDelta from "./StatDelta";
import StatPicker from "./StatPicker";

const GROUPS = [
  ["traditional", "Traditional"],
  ["pitching", "Pitch-level"],
];

// Scoreboard tiles for the stats the viewer picked, each with recent-form vs season.
export default function StatTiles({ stats, recent, recentGames }) {
  const { statDefs } = useAuth();
  const [keys, setKeys] = useTilePrefs();
  const [customizing, setCustomizing] = useState(false);
  const shown = new Set(keys);

  return (
    <section className="stats-section">
      <div className="section-head">
        <h3 className="section-title">Scoreboard</h3>
        <span className="muted small">
          {recent ? `▲▼ = last ${recentGames} games vs season` : "Recent-form trends appear after a few more games"}
        </span>
        <button className="btn ghost" onClick={() => setCustomizing((c) => !c)} aria-expanded={customizing}>
          {customizing ? "Done" : "Customize stats"}
        </button>
      </div>

      {customizing && (
        <StatPicker definitions={statDefs} selected={keys} onChange={setKeys} values={stats} />
      )}

      <div className="tiles-wrap">
        {GROUPS.map(([group, label]) => {
          const defs = statDefs.filter((d) => d.group === group && shown.has(d.key));
          if (!defs.length) return null;
          return (
            <div className="tiles-group" key={group}>
              <h4>{label}</h4>
              <div className="tiles">
                {defs.map((d) => (
                  <div className="tile" key={d.key} title={d.description}>
                    <div className="tile-label">{d.label}</div>
                    <div className="tile-value">{formatStat(d, stats[d.key])}</div>
                    {recent && (
                      <StatDelta def={d} season={stats[d.key]} recent={recent[d.key]} recentGames={recentGames} />
                    )}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
