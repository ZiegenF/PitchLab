import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import ArsenalTable from "../components/ArsenalTable";
import Avatar from "../components/Avatar";
import CoachsCorner from "../components/CoachsCorner";
import { DataSourcePanel } from "../components/DataSource";
import GameForm from "../components/GameForm";
import GameLog from "../components/GameLog";
import Goals from "../components/Goals";
import PitcherForm from "../components/PitcherForm";
import StatTiles from "../components/StatTiles";
import TrackButton from "../components/TrackButton";
import TrendChart from "../components/TrendChart";
import ZonePlot from "../components/ZonePlot";
import { LEVEL_LABEL, affiliationLabel, classLabel } from "../levels";

export default function PlayerPage() {
  const { id } = useParams();
  const pitcherId = Number(id);
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [selectedGame, setSelectedGame] = useState(null);
  const [editing, setEditing] = useState(false);
  const [addingGame, setAddingGame] = useState(false);

  useEffect(() => {
    setSelectedGame(null);
    setAddingGame(false);
  }, [pitcherId]);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    Promise.all([
      api.dashboard(pitcherId),
      api.arsenal(pitcherId),
      api.trend(pitcherId),
      api.games(pitcherId),
    ])
      .then(([dashboard, arsenal, trend, games]) => {
        if (!cancelled) setData({ ...dashboard, arsenal, trend, games });
      })
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [pitcherId, reloadKey]);

  const refresh = () => setReloadKey((k) => k + 1);

  if (error) {
    return (
      <div className="card empty">
        <h3 className="section-title">Couldn't load this pitcher</h3>
        <p className="muted">{error}</p>
        <Link to="/scout">Back to Scout players</Link>
      </div>
    );
  }
  if (!data || data.pitcher.id !== pitcherId) return <p className="muted">Loading…</p>;

  const p = data.pitcher;
  const hasPitchData = data.arsenal.length > 0;

  return (
    <>
      <header className="player-hero">
        <div className="player-hero-photo">
          <Avatar name={p.name} src={p.photo_url} size={112} />
        </div>
        <div className="player-hero-text">
          <div className="player-hero-tags">
            {p.team && <span className="tag tag-team">{p.team}</span>}
            {p.level && <span className="tag">{LEVEL_LABEL[p.level]}</span>}
            {classLabel(p) && <span className="tag">{classLabel(p)}</span>}
            {affiliationLabel(p) && <span className="tag">{affiliationLabel(p)}</span>}
            {p.in_portal && <span className="tag tag-portal">⇄ In transfer portal</span>}
            <span className="tag">{p.role === "SP" ? "Starting pitcher" : "Relief pitcher"}</span>
            <span className="tag">Throws {p.throws === "L" ? "left" : "right"}</span>
            <span className="tag">{p.is_mine ? "Your player" : "League"}</span>
          </div>
          <h2 className="player-name">{p.name}</h2>
          {p.hometown && <p className="hometown">Hometown: {p.hometown}</p>}
        </div>
        <div className="player-hero-actions">
          <TrackButton pitcher={p} onChange={refresh} />
          {p.is_mine && (
            <button className="btn on-board" onClick={() => setEditing(true)}>
              Edit profile
            </button>
          )}
        </div>
      </header>

      <StatTiles stats={data.stats} recent={data.recent} recentGames={data.recent_games} />
      <DataSourcePanel pitcher={p} />

      <div className="grid-2 coach-row">
        <CoachsCorner pitcherId={p.id} reloadKey={reloadKey} />
        <Goals pitcherId={p.id} reloadKey={reloadKey} />
      </div>

      {hasPitchData ? (
        <>
          <section className="card">
            <h3 className="section-title">Arsenal</h3>
            <ArsenalTable arsenal={data.arsenal} />
          </section>
          <div className="grid-2">
            <section className="card">
              <TrendChart trend={data.trend} />
            </section>
            <section className="card">
              <ZonePlot
                pitcherId={p.id}
                arsenal={data.arsenal}
                game={selectedGame}
                onClearGame={() => setSelectedGame(null)}
              />
            </section>
          </div>
        </>
      ) : (
        <p className="muted small">
          No pitch-by-pitch data yet.{" "}
          {p.is_mine && "Upload a Statcast or bullpen CSV from your dugout to unlock the arsenal, velocity and location charts."}
        </p>
      )}

      <section className="card">
        <div className="card-header">
          <h3 className="section-title">Box score</h3>
          {p.is_mine && !addingGame && (
            <button className="btn ghost" onClick={() => setAddingGame(true)}>
              + Add game
            </button>
          )}
        </div>
        {addingGame && (
          <GameForm
            pitcherId={p.id}
            onSaved={() => {
              setAddingGame(false);
              refresh();
            }}
            onCancel={() => setAddingGame(false)}
          />
        )}
        {hasPitchData && <p className="muted small">Click a game to plot its pitch locations.</p>}
        <GameLog
          games={data.games}
          canEdit={p.is_mine}
          selectedId={selectedGame?.id}
          onSelect={(g) => setSelectedGame((cur) => (cur?.id === g.id ? null : g))}
          onDelete={(g) =>
            api
              .deleteGame(p.id, g.id)
              .then(() => {
                if (selectedGame?.id === g.id) setSelectedGame(null);
                refresh();
              })
              .catch((e) => setError(e.message))
          }
        />
      </section>

      <PitcherForm
        open={editing}
        pitcher={p}
        onClose={() => setEditing(false)}
        onSaved={() => {
          setEditing(false);
          refresh();
        }}
        onDeleted={() => {
          setEditing(false);
          navigate("/dugout");
        }}
      />
    </>
  );
}
