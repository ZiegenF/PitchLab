import { formatStat } from "../stats";

const GROUPS = [
  ["traditional", "Traditional"],
  ["pitching", "Pitch-level"],
];

// Checklist of every stat in the registry. `selected` is an array of keys.
export default function StatPicker({ definitions, selected, onChange, values }) {
  const shown = new Set(selected);

  function toggle(key) {
    const next = new Set(shown);
    next.has(key) ? next.delete(key) : next.add(key);
    onChange(definitions.map((d) => d.key).filter((k) => next.has(k))); // keep registry order
  }

  return (
    <div className="card customize-panel">
      <div className="card-header">
        <h3>Choose your stats</h3>
        <button className="link" onClick={() => onChange(null)}>
          Reset to defaults
        </button>
      </div>
      <div className="customize-groups">
        {GROUPS.map(([group, label]) => (
          <fieldset key={group}>
            <legend>{label}</legend>
            {definitions
              .filter((d) => d.group === group)
              .map((d) => (
                <label key={d.key} className="checkbox stat-option">
                  <input type="checkbox" checked={shown.has(d.key)} onChange={() => toggle(d.key)} />
                  <span>
                    <strong>{d.label}</strong>
                    {values && <span className="muted"> {formatStat(d, values[d.key])}</span>}
                    <span className="muted small stat-desc">{d.description}</span>
                  </span>
                </label>
              ))}
          </fieldset>
        ))}
      </div>
    </div>
  );
}
