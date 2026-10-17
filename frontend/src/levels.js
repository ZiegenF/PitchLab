// Competition levels, lowest to highest. Keys match the API's `level` field.
export const LEVELS = ["HS", "NCAA", "A", "A+", "AA", "AAA", "MLB"];
export const MINOR_LEVELS = ["AAA", "AA", "A+", "A"];

export const LEVEL_LABEL = {
  HS: "High school",
  NCAA: "College",
  A: "Single-A",
  "A+": "High-A",
  AA: "Double-A",
  AAA: "Triple-A",
  MLB: "MLB",
};

export const COLLEGE_CLASSES = [
  ["FR", "Freshman"],
  ["SO", "Sophomore"],
  ["JR", "Junior"],
  ["SR", "Senior"],
  ["GR", "Graduate"],
];
const CLASS_LABEL = Object.fromEntries(COLLEGE_CLASSES);

// The tabs on the Scout page, in career order. "unset" only shows when someone has no level.
export const LEVEL_GROUPS = [
  { key: "all", label: "All levels", blurb: "Every pitcher at every level.", match: () => true },
  { key: "hs", label: "High school", blurb: "Prep arms, with grad year and college commitment.", match: (p) => p.level === "HS" },
  { key: "college", label: "College", blurb: "NCAA pitchers by class.", match: (p) => p.level === "NCAA" },
  {
    key: "portal",
    label: "Transfer portal",
    blurb: "College pitchers who have entered the transfer portal.",
    match: (p) => p.level === "NCAA" && p.in_portal,
  },
  { key: "minors", label: "Minor leagues", blurb: "Triple-A down to Single-A, with parent club.", match: (p) => MINOR_LEVELS.includes(p.level) },
  { key: "mlb", label: "MLB", blurb: "Major league pitchers.", match: (p) => p.level === "MLB" },
  { key: "unset", label: "No level", blurb: "Pitchers without a level yet. Edit them to set one.", match: (p) => !p.level },
];

export function classLabel(p) {
  if (!p.class_year) return null;
  if (p.level === "HS") return `Class of ${p.class_year}`;
  return CLASS_LABEL[p.class_year] ?? p.class_year;
}

// "NYY org" for minor leaguers, "Committed to Texas" for high schoolers.
export function affiliationLabel(p) {
  if (!p.affiliation) return null;
  if (MINOR_LEVELS.includes(p.level)) return `${p.affiliation} org`;
  if (p.level === "HS") return `Committed to ${p.affiliation}`;
  return p.affiliation;
}

export const affiliationField = (level) =>
  MINOR_LEVELS.includes(level)
    ? { label: "Parent club", placeholder: "NYY" }
    : level === "HS"
      ? { label: "College commitment", placeholder: "Uncommitted" }
      : null;
