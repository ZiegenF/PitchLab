import { formatDiff, trendOf } from "../stats";

// ▲/▼ with the change and whether that's good. Never color alone: icon + words carry it too.
export default function StatDelta({ def, season, recent, recentGames, compact = false }) {
  const t = trendOf(def, season, recent);
  if (!t) return compact ? null : <span className="delta muted">—</span>;
  if (t.dir === "flat") return <span className="delta muted">steady</span>;
  const label = `${t.good ? "Better" : "Worse"} over last ${recentGames} games: ${formatDiff(def, t.diff)}`;
  return (
    <span className={`delta ${t.good ? "good" : "bad"}`} title={label} aria-label={label}>
      <span aria-hidden="true">{t.dir === "up" ? "▲" : "▼"}</span> {formatDiff(def, t.diff)}
    </span>
  );
}
