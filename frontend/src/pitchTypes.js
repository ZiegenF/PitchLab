// Color follows the pitch type (the entity), never its rank in a given pitcher's arsenal,
// so a slider is the same color on every dashboard. Values are CSS vars set in styles.css.
export const PITCH_TYPES = {
  FF: { name: "4-Seam Fastball", color: "var(--series-1)" },
  SI: { name: "Sinker", color: "var(--series-2)" },
  SL: { name: "Slider", color: "var(--series-3)" },
  CH: { name: "Changeup", color: "var(--series-4)" },
  CU: { name: "Curveball", color: "var(--series-5)" },
  FC: { name: "Cutter", color: "var(--series-6)" },
  ST: { name: "Sweeper", color: "var(--series-7)" },
  FS: { name: "Splitter", color: "var(--series-8)" },
};

// Rarer Statcast codes: named, but drawn in muted ink rather than a ninth series color.
const OTHER_NAMES = {
  KC: "Knuckle Curve", SV: "Slurve", FT: "2-Seam Fastball", FO: "Forkball", SC: "Screwball",
  KN: "Knuckleball", EP: "Eephus", CS: "Slow Curve", FA: "Fastball", PO: "Pitchout",
  UN: "Untracked",
};

export const pitchName = (t) => PITCH_TYPES[t]?.name ?? OTHER_NAMES[t] ?? t;
export const pitchColor = (t) => PITCH_TYPES[t]?.color ?? "var(--text-muted)";

// Zone plot outcome groups - three categories, which keeps scatter colors distinguishable
// for colorblind readers.
export const OUTCOMES = {
  strike: { label: "Called / swinging strike", color: "var(--series-1)" },
  ball: { label: "Ball", color: "var(--series-2)" },
  contact: { label: "Foul / in play", color: "var(--series-3)" },
};

export function outcomeOf(result) {
  if (result === "called_strike" || result === "swinging_strike") return "strike";
  if (result === "foul" || result === "in_play") return "contact";
  return "ball";
}

export const fmt = (v, digits = 1, suffix = "") =>
  v == null ? "—" : `${Number(v).toFixed(digits)}${suffix}`;
