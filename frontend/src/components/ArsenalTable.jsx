import { fmt, pitchColor, pitchName } from "../pitchTypes";

const COLS = [
  ["usage_pct", "Usage", 1, "%"],
  ["avg_velo", "Velo", 1, ""],
  ["max_velo", "Max", 1, ""],
  ["avg_spin", "Spin", 0, ""],
  ["zone_pct", "Zone%", 1, ""],
  ["whiff_pct", "Whiff%", 1, ""],
  ["chase_pct", "Chase%", 1, ""],
  ["csw_pct", "CSW%", 1, ""],
];

export default function ArsenalTable({ arsenal }) {
  const maxUsage = Math.max(...arsenal.map((a) => a.usage_pct ?? 0), 1);
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th className="left">Pitch</th>
            <th className="left usage-col">Usage</th>
            {COLS.slice(1).map(([k, label]) => (
              <th key={k}>{label}</th>
            ))}
            <th>#</th>
          </tr>
        </thead>
        <tbody>
          {arsenal.map((a) => (
            <tr key={a.pitch_type}>
              <td className="left">
                <span className="swatch" style={{ background: pitchColor(a.pitch_type) }} />
                {pitchName(a.pitch_type)} <span className="muted">{a.pitch_type}</span>
              </td>
              <td className="left usage-col">
                <div className="usage-bar">
                  <div
                    className="usage-fill"
                    style={{
                      width: `${(a.usage_pct / maxUsage) * 100}%`,
                      background: pitchColor(a.pitch_type),
                    }}
                  />
                  <span className="usage-label">{fmt(a.usage_pct, 1, "%")}</span>
                </div>
              </td>
              {COLS.slice(1).map(([k, , digits]) => (
                <td key={k}>{fmt(a[k], digits)}</td>
              ))}
              <td className="muted">{a.pitches.toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
