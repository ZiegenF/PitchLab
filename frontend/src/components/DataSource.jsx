import { LEVEL_LABEL } from "../levels";

// How each source is described. Status always pairs an icon with words, never color alone.
const SOURCES = {
  simulated: { icon: "◇", tag: "Simulated data", tone: "muted" },
  mlb: { icon: "✓", tag: "Official MLB data", tone: "good" },
  csv: { icon: "↑", tag: "Uploaded CSV", tone: "muted" },
  manual: { icon: "✎", tag: "Entered by hand", tone: "muted" },
};

const CHECK_LABELS = {
  games: "G", outs: "IP", hits: "H", runs: "R", earned_runs: "ER", walks: "BB",
  strikeouts: "K", home_runs: "HR", hit_by_pitch: "HBP", batters_faced: "BF", era: "ERA",
};

const ip = (outs) => (outs == null ? "—" : `${Math.floor(outs / 3)}.${outs % 3}`);
const show = (stat, v) => (v == null ? "—" : stat === "outs" ? ip(v) : stat === "era" ? v.toFixed(2) : v);
const day = (iso) => new Date(iso + (iso.endsWith("Z") ? "" : "Z")).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });

function mlbStatus(p) {
  const v = p.verification;
  if (!v) return { icon: "?", tag: "MLB data, not checked yet", tone: "muted" };
  if (!v.ok) return { icon: "⚠", tag: "Doesn't match official totals", tone: "bad" };
  return SOURCES.mlb;
}

export function sourceInfo(p) {
  if (p.source === "mlb") return mlbStatus(p);
  return SOURCES[p.source] ?? null;
}

// One-line label for cards.
export function SourceTag({ pitcher }) {
  const s = sourceInfo(pitcher);
  if (!s) return null;
  return (
    <span className={`source-tag source-${s.tone}`}>
      <span aria-hidden="true">{s.icon}</span> {s.tag}
    </span>
  );
}

function Verification({ v }) {
  return (
    <details className="verify" open={v.levels.length > 1}>
      <summary>
        Checked against MLB's official {v.season} totals on {day(v.checked_at)}
      </summary>
      {v.levels.map((lv) => (
        <div key={lv.level} className="table-scroll">
          <table className="data-table verify-table">
            <caption>
              {LEVEL_LABEL[lv.level]} · {lv.ok ? "✓ every stat matches" : "⚠ mismatch"}
            </caption>
            <thead>
              <tr>
                <th className="left">Source</th>
                {lv.checks.map((c) => (
                  <th key={c.stat}>{CHECK_LABELS[c.stat] ?? c.stat}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {["ours", "official"].map((who) => (
                <tr key={who}>
                  <td className="left">{who === "ours" ? "PitchLab" : "MLB official"}</td>
                  {lv.checks.map((c) => (
                    <td key={c.stat} className={c.ours !== c.official ? "mismatch" : ""}>
                      {show(c.stat, c[who])}
                      {who === "ours" && c.ours !== c.official && <span className="sr-only"> (differs)</span>}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </details>
  );
}

// "Where these numbers come from" panel for the player page.
export function DataSourcePanel({ pitcher: p }) {
  const s = sourceInfo(p);
  if (!s) return null;
  const v = p.verification;
  const pitches = v?.pitches;

  let body;
  if (p.source === "simulated") {
    body = (
      <p>
        These numbers are <strong>generated for the demo</strong>, not this player's real
        stats. The season is simulated pitch by pitch, so the stats are consistent with each
        other, but none of it happened.
      </p>
    );
  } else if (p.source === "mlb") {
    body = (
      <>
        <p>
          Box scores (innings, hits, runs, earned runs, walks, strikeouts) come from the{" "}
          <strong>MLB Stats API</strong>, which reports the official scorer's numbers.
          {pitches && " Pitch data (velocity, spin, location) comes from Statcast."}
          {p.synced_at && ` Last synced ${day(p.synced_at)}.`}
        </p>
        {v?.levels.length > 1 && (
          <p>
            He pitched at {v.levels.length} levels this season. The stats above are his{" "}
            {LEVEL_LABEL[p.level]} games only, matching how MLB reports splits; every level's
            official line is in the table below.
          </p>
        )}
        {pitches && (
          <p className={pitches.loaded === pitches.official ? "good-text" : "error-text"}>
            <span aria-hidden="true">{pitches.loaded === pitches.official ? "✓ " : "⚠ "}</span>
            Statcast pitches: {pitches.loaded.toLocaleString()} of {pitches.official.toLocaleString()} official
          </p>
        )}
        {v && <Verification v={v} />}
      </>
    );
  } else if (p.source === "csv") {
    body = (
      <p>
        Box scores are counted from the pitch-by-pitch events in an uploaded CSV. Statcast doesn't
        say which runs were earned, so <strong>every run counts as earned</strong> and ERA can
        run high.
      </p>
    );
  } else {
    body = <p>Box scores were entered by hand.</p>;
  }

  return (
    <section className={`card data-source source-${s.tone}`}>
      <h3 className="section-title">
        <span aria-hidden="true">{s.icon}</span> {s.tag}
      </h3>
      {body}
    </section>
  );
}
