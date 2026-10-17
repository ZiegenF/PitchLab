// Formatting and trend helpers driven by the API's stat registry (GET /api/stats).

export function formatStat(def, value) {
  if (value == null) return "—";
  if (typeof value === "string") return value;
  let s = def.digits === 0 ? Math.round(value).toLocaleString() : value.toFixed(def.digits);
  if (def.digits === 3 && Math.abs(value) < 1) s = s.replace(/^(-?)0/, "$1"); // baseball style: .245
  return s + def.suffix;
}

/**
 * Recent form vs season for a stat with a good/bad direction.
 * Returns null when there's nothing meaningful to show.
 */
export function trendOf(def, season, recent) {
  if (!def?.better || typeof season !== "number" || typeof recent !== "number") return null;
  const diff = recent - season;
  if (Math.abs(diff) < 0.5 * 10 ** -def.digits) return { dir: "flat", good: null, diff: 0 };
  return {
    dir: diff > 0 ? "up" : "down",
    good: def.better === "higher" ? diff > 0 : diff < 0,
    diff,
  };
}

export function formatDiff(def, diff) {
  const abs = formatStat({ ...def, suffix: def.suffix === "%" ? " pts" : def.suffix }, Math.abs(diff));
  return `${diff > 0 ? "+" : "−"}${abs}`;
}

export const defsByKey = (defs) => Object.fromEntries(defs.map((d) => [d.key, d]));
