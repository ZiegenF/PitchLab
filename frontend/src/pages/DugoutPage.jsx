import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth, useTilePrefs } from "../auth";
import BaseballCard from "../components/BaseballCard";
import LevelTabs from "../components/LevelTabs";
import PitcherForm from "../components/PitcherForm";
import StatDelta from "../components/StatDelta";
import StatPicker from "../components/StatPicker";
import UploadCsv from "../components/UploadCsv";
import { GOAL_STATUS } from "../components/Goals";
import { LEVEL_GROUPS } from "../levels";
import { defsByKey, formatStat } from "../stats";

const CARD_STAT_LIMIT = 6;

function SignedOut() {
  return (
    <div className="hero card">
      <h2 className="hero-title">Your own dugout</h2>
      <p>
        Create a free account to build a dashboard of the pitchers you care about: your own arms,
        your team, or anyone in the league. Track the stats you choose, set goals, and get
        suggestions when a trend starts heading the wrong way.
      </p>
      <div className="hero-actions">
        <Link className="btn primary" to="/signup">
          Create account
        </Link>
        <Link className="btn ghost" to="/login">
          Sign in
        </Link>
        <Link className="link" to="/scout">
          or browse league pitchers
        </Link>
      </div>
    </div>
  );
}

function goalSummary(goals) {
  if (!goals.length) return null;
  const counts = {};
  goals.forEach((g) => (counts[g.status] = (counts[g.status] ?? 0) + 1));
  return Object.entries(GOAL_STATUS)
    .filter(([k]) => counts[k])
    .map(([k, s]) => (
      <span key={k} className={`goal-badge goal-${k}`}>
        <span aria-hidden="true">{s.icon}</span> {counts[k]} {s.label.toLowerCase()}
      </span>
    ));
}

// Side-by-side table: every tracked pitcher × every chosen stat, best in each column marked.
function Comparison({ players, defs, recentNote }) {
  const best = {};
  for (const d of defs) {
    if (!d.better) continue;
    const vals = players.map((p) => p.season[d.key]).filter((v) => typeof v === "number");
    if (vals.length > 1) best[d.key] = d.better === "higher" ? Math.max(...vals) : Math.min(...vals);
  }
  return (
    <section className="card">
      <div className="card-header">
        <h3 className="section-title">Side by side</h3>
        <span className="muted small">★ best in the dugout · {recentNote}</span>
      </div>
      <div className="table-scroll">
        <table className="data-table box-score">
          <thead>
            <tr>
              <th className="left">Pitcher</th>
              {defs.map((d) => (
                <th key={d.key} title={d.description}>
                  {d.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {players.map((p) => (
              <tr key={p.pitcher.id}>
                <td className="left">
                  <Link to={`/players/${p.pitcher.id}`}>{p.pitcher.name}</Link>
                </td>
                {defs.map((d) => {
                  const v = p.season[d.key];
                  const isBest = best[d.key] !== undefined && v === best[d.key];
                  return (
                    <td key={d.key} className={isBest ? "best" : ""}>
                      {isBest && <span aria-label="best">★ </span>}
                      {formatStat(d, v)}
                      {p.recent && (
                        <div>
                          <StatDelta def={d} season={v} recent={p.recent[d.key]} recentGames={p.recent_games} compact />
                        </div>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function DugoutPage() {
  const { user, loading, statDefs } = useAuth();
  const [keys, setKeys] = useTilePrefs();
  const navigate = useNavigate();
  const [players, setPlayers] = useState(null);
  const [error, setError] = useState(null);
  const [customizing, setCustomizing] = useState(false);
  const [adding, setAdding] = useState(false);
  const [level, setLevel] = useState("all");

  // only the levels your dugout actually has; the switcher hides when there's just one
  const groups = useMemo(() => {
    if (!players) return [];
    return LEVEL_GROUPS.map((g) => ({ ...g, count: players.filter((p) => g.match(p.pitcher)).length }))
      .filter((g) => g.key === "all" || g.count > 0);
  }, [players]);
  const group = groups.find((g) => g.key === level) ?? LEVEL_GROUPS[0];
  const shown = players?.filter((p) => group.match(p.pitcher));

  const load = useCallback(() => {
    api.myDashboard().then((d) => setPlayers(d.players)).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  if (loading) return <p className="muted">Loading…</p>;
  if (!user) return <SignedOut />;

  const defs = defsByKey(statDefs);
  const chosen = keys.map((k) => defs[k]).filter(Boolean);

  return (
    <>
      <header className="page-head">
        <div>
          <h2 className="page-title">{user.display_name}'s Dugout</h2>
          <p className="muted">
            {players ? `${players.length} pitcher${players.length === 1 ? "" : "s"} tracked` : "Loading…"}
          </p>
        </div>
        <div className="page-actions">
          <button className="btn ghost" onClick={() => setCustomizing((c) => !c)} aria-expanded={customizing}>
            {customizing ? "Done" : "Customize stats"}
          </button>
          <Link className="btn ghost" to="/scout">
            Scout players
          </Link>
          <button className="btn primary" onClick={() => setAdding(true)}>
            + Add pitcher
          </button>
        </div>
      </header>

      {error && <div className="error" role="alert">{error}</div>}
      {customizing && <StatPicker definitions={statDefs} selected={keys} onChange={setKeys} />}

      {players && players.length === 0 && (
        <div className="card empty">
          <h3 className="section-title">Your dugout is empty</h3>
          <p className="muted">
            Add your own pitcher, upload a CSV, or <Link to="/scout">scout league pitchers</Link> and
            add them to your dugout.
          </p>
        </div>
      )}

      {groups.length > 2 && <LevelTabs groups={groups} value={group.key} onChange={setLevel} label="Dugout level" />}

      {shown && shown.length > 0 && (
        <>
          <div className="card-grid">
            {shown.map((p) => (
              <BaseballCard
                key={p.pitcher.id}
                pitcher={p.pitcher}
                to={`/players/${p.pitcher.id}`}
                badge={p.pitcher.is_mine ? "Yours" : null}
                recentGames={p.recent_games}
                stats={chosen.slice(0, CARD_STAT_LIMIT).map((d) => ({
                  def: d,
                  value: p.season[d.key],
                  recent: p.recent ? p.recent[d.key] : undefined,
                }))}
              >
                {p.focus ? (
                  <p className="focus">
                    <span className="focus-label">
                      <span aria-hidden="true">▼</span> Work on
                    </span>{" "}
                    {p.focus.title}
                  </p>
                ) : p.improving > 0 ? (
                  <p className="focus">
                    <span className="focus-label good-text">
                      <span aria-hidden="true">▲</span> Trending up
                    </span>{" "}
                    {p.improving} stat{p.improving === 1 ? "" : "s"} improving
                  </p>
                ) : null}
                {p.goals.length > 0 && <div className="goal-summary">{goalSummary(p.goals)}</div>}
              </BaseballCard>
            ))}
          </div>

          {chosen.length > 0 && (
            <Comparison
              players={shown}
              defs={chosen}
              recentNote={`▲▼ last ${shown[0].recent_games} games vs season`}
            />
          )}
        </>
      )}

      <section className="card upload-card">
        <UploadCsv onUploaded={load} />
      </section>

      <PitcherForm
        open={adding}
        pitcher={null}
        onClose={() => setAdding(false)}
        onSaved={(saved) => {
          setAdding(false);
          navigate(`/players/${saved.id}`);
        }}
        onDeleted={() => setAdding(false)}
      />
    </>
  );
}
