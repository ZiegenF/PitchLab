import { useRef } from "react";

/**
 * Level switcher. Click a tab, use ← → (wraps around), or the ‹ › buttons to cycle.
 *   groups: [{ key, label, count }]
 */
export default function LevelTabs({ groups, value, onChange, label = "Level" }) {
  const refs = useRef({});
  const idx = Math.max(0, groups.findIndex((g) => g.key === value));

  function go(i, focus) {
    const g = groups[(i + groups.length) % groups.length];
    onChange(g.key);
    if (focus) refs.current[g.key]?.focus();
  }

  function onKeyDown(e) {
    const moves = { ArrowRight: idx + 1, ArrowLeft: idx - 1, Home: 0, End: groups.length - 1 };
    if (e.key in moves) {
      e.preventDefault();
      go(moves[e.key], true);
    }
  }

  return (
    <div className="level-tabs">
      <button type="button" className="level-step" onClick={() => go(idx - 1)} aria-label="Previous level">
        ‹
      </button>
      <div role="tablist" aria-label={label} className="level-tablist" onKeyDown={onKeyDown}>
        {groups.map((g) => {
          const active = g.key === groups[idx]?.key;
          return (
            <button
              key={g.key}
              ref={(el) => (refs.current[g.key] = el)}
              role="tab"
              type="button"
              aria-selected={active}
              tabIndex={active ? 0 : -1}
              className={active ? "level-tab active" : "level-tab"}
              onClick={() => onChange(g.key)}
            >
              {g.label}
              <span className="level-count">{g.count}</span>
            </button>
          );
        })}
      </div>
      <button type="button" className="level-step" onClick={() => go(idx + 1)} aria-label="Next level">
        ›
      </button>
    </div>
  );
}
