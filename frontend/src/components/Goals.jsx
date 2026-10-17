import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { defsByKey, formatStat } from "../stats";

export const GOAL_STATUS = {
  met: { icon: "✓", label: "Met" },
  on_track: { icon: "↗", label: "On track" },
  off_track: { icon: "↘", label: "Off track" },
  no_data: { icon: "–", label: "No data yet" },
};

export function GoalBadge({ status }) {
  const s = GOAL_STATUS[status];
  return (
    <span className={`goal-badge goal-${status}`}>
      <span aria-hidden="true">{s.icon}</span> {s.label}
    </span>
  );
}

export default function Goals({ pitcherId, reloadKey, onChange }) {
  const { user, statDefs } = useAuth();
  const location = useLocation();
  const [goals, setGoals] = useState([]);
  const [statKey, setStatKey] = useState("");
  const [target, setTarget] = useState("");
  const [error, setError] = useState(null);
  const defs = defsByKey(statDefs);
  const goalable = statDefs.filter((d) => d.better);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    api.goals(pitcherId).then((g) => !cancelled && setGoals(g));
    return () => {
      cancelled = true;
    };
  }, [user, pitcherId, reloadKey]);

  if (!user) {
    return (
      <section className="card">
        <h3 className="section-title">Goals</h3>
        <p className="muted small">
          <Link to="/login" state={{ from: location.pathname }}>Sign in</Link> to set targets like
          "BB/9 under 3.0" and see whether recent games are moving toward them.
        </p>
      </section>
    );
  }

  const selected = defs[statKey];

  async function add(e) {
    e.preventDefault();
    setError(null);
    try {
      const g = await api.addGoal(pitcherId, { stat_key: statKey, target: Number(target) });
      setGoals((gs) => [...gs, g]);
      setTarget("");
      onChange?.();
    } catch (err) {
      setError(err.message);
    }
  }

  async function remove(id) {
    await api.deleteGoal(id);
    setGoals((gs) => gs.filter((g) => g.id !== id));
    onChange?.();
  }

  return (
    <section className="card">
      <h3 className="section-title">Goals</h3>
      {goals.length === 0 && <p className="muted small">No goals yet. Pick a stat to improve.</p>}
      <ul className="goals">
        {goals.map((g) => {
          const d = defs[g.stat_key];
          if (!d) return null;
          return (
            <li key={g.id} className="goal">
              <div className="goal-main">
                <strong>{d.label}</strong>{" "}
                <span className="muted">
                  {d.better === "lower" ? "≤" : "≥"} {formatStat(d, g.target)}
                </span>
                <div className="small muted">
                  Season {formatStat(d, g.season)}
                  {g.recent != null && <> · Recent {formatStat(d, g.recent)}</>}
                </div>
              </div>
              <GoalBadge status={g.status} />
              <button className="icon-btn" onClick={() => remove(g.id)} aria-label={`Remove ${d.label} goal`}>
                ×
              </button>
            </li>
          );
        })}
      </ul>
      <form className="goal-form" onSubmit={add}>
        <label className="field">
          <span>Stat</span>
          <select value={statKey} onChange={(e) => setStatKey(e.target.value)} required>
            <option value="" disabled>
              Choose…
            </option>
            {goalable.map((d) => (
              <option key={d.key} value={d.key}>
                {d.label} ({d.better} is better)
              </option>
            ))}
          </select>
        </label>
        <label className="field narrow-wide">
          <span>Target {selected ? (selected.better === "lower" ? "(at or under)" : "(at or over)") : ""}</span>
          <input
            type="number"
            step="any"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder={selected?.suffix === "%" ? "e.g. 30" : "e.g. 3.0"}
            required
          />
        </label>
        <button className="btn primary" type="submit">
          Set goal
        </button>
      </form>
      {error && <p className="small error-text" role="alert">{error}</p>}
    </section>
  );
}
