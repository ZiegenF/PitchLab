import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { OUTCOMES, fmt, outcomeOf, pitchName } from "../pitchTypes";

// Catcher's view, in feet. Matches the zone used by the API (analytics.py).
const ZONE = { left: -0.83, right: 0.83, bottom: 1.5, top: 3.5 };
const VIEW = { xMin: -2.2, xMax: 2.2, zMin: 0.3, zMax: 4.7 };
const W = 360;
const H = 360;
const sx = (x) => ((x - VIEW.xMin) / (VIEW.xMax - VIEW.xMin)) * W;
const sz = (z) => H - ((z - VIEW.zMin) / (VIEW.zMax - VIEW.zMin)) * H;

const RESULT_LABEL = {
  ball: "Ball",
  called_strike: "Called strike",
  swinging_strike: "Swinging strike",
  foul: "Foul",
  in_play: "In play",
  hit_by_pitch: "Hit by pitch",
};

const inZone = (p) =>
  Math.abs(p.plate_x) <= ZONE.right && p.plate_z >= ZONE.bottom && p.plate_z <= ZONE.top;

export default function ZonePlot({ pitcherId, arsenal, game, onClearGame }) {
  const [pitchType, setPitchType] = useState("");
  const [pitches, setPitches] = useState([]);
  const [hover, setHover] = useState(null);

  useEffect(() => setPitchType(""), [pitcherId]);

  useEffect(() => {
    let cancelled = false;
    api
      .pitches(pitcherId, { pitch_type: pitchType, appearance_id: game?.id, limit: 800 })
      .then((rows) => !cancelled && setPitches(rows.filter((p) => p.plate_x != null)));
    return () => {
      cancelled = true;
    };
  }, [pitcherId, pitchType, game?.id]);

  const counts = useMemo(() => {
    const c = { strike: 0, ball: 0, contact: 0 };
    pitches.forEach((p) => c[outcomeOf(p.result)]++);
    return c;
  }, [pitches]);
  const zonePct = pitches.length ? (pitches.filter(inZone).length / pitches.length) * 100 : null;

  const cellW = (ZONE.right - ZONE.left) / 3;
  const cellH = (ZONE.top - ZONE.bottom) / 3;

  return (
    <>
      <div className="card-header">
        <h3>Pitch locations</h3>
        <span className="muted small">
          {game ? (
            <>
              {game.game_date} vs {game.opponent}{" "}
              <button className="link" onClick={onClearGame}>
                show season
              </button>
            </>
          ) : pitches.length >= 800 ? (
            "most recent 800"
          ) : (
            "season"
          )}
        </span>
      </div>

      <div className="chips" role="group" aria-label="Filter by pitch type">
        <button className={pitchType === "" ? "chip active" : "chip"} onClick={() => setPitchType("")}>
          All
        </button>
        {arsenal.map((a) => (
          <button
            key={a.pitch_type}
            className={pitchType === a.pitch_type ? "chip active" : "chip"}
            onClick={() => setPitchType(a.pitch_type)}
          >
            {a.pitch_type}
          </button>
        ))}
      </div>

      <div className="zone-wrap">
        <svg viewBox={`0 0 ${W} ${H}`} className="zone-svg" role="img"
          aria-label={`Pitch location plot, ${pitches.length} pitches, catcher's view`}>
          {/* zone and 3x3 grid */}
          {[1, 2].map((i) => (
            <g key={i} className="zone-grid">
              <line x1={sx(ZONE.left + i * cellW)} x2={sx(ZONE.left + i * cellW)} y1={sz(ZONE.top)} y2={sz(ZONE.bottom)} />
              <line x1={sx(ZONE.left)} x2={sx(ZONE.right)} y1={sz(ZONE.bottom + i * cellH)} y2={sz(ZONE.bottom + i * cellH)} />
            </g>
          ))}
          <rect className="zone-rect" x={sx(ZONE.left)} y={sz(ZONE.top)}
            width={sx(ZONE.right) - sx(ZONE.left)} height={sz(ZONE.bottom) - sz(ZONE.top)} />
          {/* home plate */}
          <polygon className="plate"
            points={[[-0.71, 0.55], [0.71, 0.55], [0.71, 0.45], [0, 0.35], [-0.71, 0.45]]
              .map(([x, z]) => `${sx(x)},${sz(z)}`).join(" ")} />

          {pitches.map((p) => (
            <circle
              key={p.id}
              cx={sx(p.plate_x)}
              cy={sz(p.plate_z)}
              r={hover?.id === p.id ? 6 : 4.5}
              fill={OUTCOMES[outcomeOf(p.result)].color}
              className="pitch-dot"
              onMouseEnter={() => setHover(p)}
              onMouseLeave={() => setHover(null)}
            />
          ))}
        </svg>

        <div className="zone-side">
          <div className="legend-list">
            {Object.entries(OUTCOMES).map(([k, o]) => (
              <div key={k} className="legend-item">
                <span className="dot" style={{ background: o.color }} />
                <span>{o.label}</span>
                <span className="muted">{counts[k]}</span>
              </div>
            ))}
          </div>
          <div className="zone-stat">
            <div className="tile-label">Zone%</div>
            <div className="tile-value">{fmt(zonePct, 1, "%")}</div>
          </div>
          <div className="hover-card" aria-live="polite">
            {hover ? (
              <>
                <strong>{pitchName(hover.pitch_type)}</strong>
                <div>{fmt(hover.velocity)} mph · {hover.spin_rate ? Math.round(hover.spin_rate) : "—"} rpm</div>
                <div>{RESULT_LABEL[hover.result] ?? hover.result} on {hover.balls}-{hover.strikes}</div>
              </>
            ) : (
              <span className="muted small">Hover a pitch for details</span>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
