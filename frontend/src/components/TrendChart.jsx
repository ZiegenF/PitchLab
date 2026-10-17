import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { pitchColor, pitchName } from "../pitchTypes";

// Velocity and spin have different scales, so they are separate views, never a dual axis.
const METRICS = {
  avg_velo: { label: "Velocity", unit: "mph", digits: 1 },
  avg_spin: { label: "Spin rate", unit: "rpm", digits: 0 },
};

const shortDate = (d) =>
  new Date(`${d}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });

function TrendTooltip({ active, payload, label, metric }) {
  if (!active || !payload?.length) return null;
  const m = METRICS[metric];
  return (
    <div className="chart-tooltip">
      <div className="tooltip-title">{shortDate(label)}</div>
      {[...payload]
        .sort((a, b) => b.value - a.value)
        .map((e) => (
          <div key={e.dataKey} className="tooltip-row">
            <span className="swatch" style={{ background: e.color }} />
            <span>{pitchName(e.dataKey)}</span>
            <strong>
              {e.value.toFixed(m.digits)} {m.unit}
            </strong>
          </div>
        ))}
    </div>
  );
}

export default function TrendChart({ trend }) {
  const [metric, setMetric] = useState("avg_velo");

  // [{game_date, pitch_type, avg_velo}] -> [{game_date, FF: 96.1, SL: 88.0}]
  const { rows, types } = useMemo(() => {
    const byDate = new Map();
    const counts = {};
    for (const t of trend) {
      if (!byDate.has(t.game_date)) byDate.set(t.game_date, { game_date: t.game_date });
      byDate.get(t.game_date)[t.pitch_type] = t[metric];
      counts[t.pitch_type] = (counts[t.pitch_type] ?? 0) + t.pitches;
    }
    const types = Object.keys(counts).sort((a, b) => counts[b] - counts[a]);
    return { rows: [...byDate.values()], types };
  }, [trend, metric]);

  const m = METRICS[metric];

  return (
    <>
      <div className="card-header">
        <h3>{m.label} by game</h3>
        <div className="segmented" role="tablist">
          {Object.entries(METRICS).map(([k, v]) => (
            <button
              key={k}
              role="tab"
              aria-selected={metric === k}
              className={metric === k ? "active" : ""}
              onClick={() => setMetric(k)}
            >
              {v.label}
            </button>
          ))}
        </div>
      </div>
      <div className="chart-box">
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis
              dataKey="game_date"
              tickFormatter={shortDate}
              stroke="var(--axis)"
              tick={{ fill: "var(--text-muted)", fontSize: 12 }}
              minTickGap={32}
              tickLine={false}
            />
            <YAxis
              domain={metric === "avg_velo" ? ["dataMin - 1", "dataMax + 1"] : ["auto", "auto"]}
              tickFormatter={(v) => Math.round(v).toLocaleString()}
              stroke="var(--axis)"
              tick={{ fill: "var(--text-muted)", fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              width={48}
            />
            <Tooltip
              content={<TrendTooltip metric={metric} />}
              cursor={{ stroke: "var(--axis)", strokeWidth: 1 }}
            />
            <Legend
              formatter={(v) => <span className="legend-text">{pitchName(v)}</span>}
              iconType="plainline"
              wrapperStyle={{ paddingTop: 8 }}
            />
            {types.map((t) => (
              <Line
                key={t}
                dataKey={t}
                stroke={pitchColor(t)}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 5, stroke: "var(--surface)", strokeWidth: 2 }}
                connectNulls
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}
