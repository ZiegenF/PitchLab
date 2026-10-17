import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import BaseballCard from "../components/BaseballCard";
import LevelTabs from "../components/LevelTabs";
import TrackButton from "../components/TrackButton";
import { LEVEL_GROUPS, LEVEL_LABEL, MINOR_LEVELS } from "../levels";
import { defsByKey } from "../stats";

const CARD_KEYS = ["era", "k_per_9", "whip"];

// value getter + direction; missing values always sort last
const SORTS = {
  name: { label: "Name", get: (p) => p.name, dir: 1 },
  era: { label: "ERA (low first)", get: (p) => p.era, dir: 1 },
  k_per_9: { label: "K/9 (high first)", get: (p) => p.k_per_9, dir: -1 },
  whip: { label: "WHIP (low first)", get: (p) => p.whip, dir: 1 },
  avg_fb_velo: { label: "FB velo (high first)", get: (p) => p.avg_fb_velo, dir: -1 },
};

function compare(sort) {
  const { get, dir } = SORTS[sort] ?? SORTS.name;
  return (a, b) => {
    const x = get(a);
    const y = get(b);
    if (x == null || y == null) return (x == null) - (y == null);
    return (typeof x === "string" ? x.localeCompare(y) : x - y) * dir;
  };
}

function Segmented({ label, options, value, onChange }) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map(([v, text]) => (
        <button key={v} type="button" className={value === v ? "active" : ""} aria-pressed={value === v} onClick={() => onChange(v)}>
          {text}
        </button>
      ))}
    </div>
  );
}

export default function ScoutPage() {
  const { user, statDefs } = useAuth();
  const [pitchers, setPitchers] = useState(null);
  const [error, setError] = useState(null);
  // filters live in the URL so a scouting view can be bookmarked or shared
  const [params, setParams] = useSearchParams();
  const level = params.get("level") ?? "all";
  const minor = params.get("minor") ?? "";
  const throws = params.get("throws") ?? "";
  const role = params.get("role") ?? "";
  const data = params.get("data") ?? "";
  const sort = params.get("sort") ?? "name";
  const query = params.get("q") ?? "";

  const setParam = (k, v) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (v) next.set(k, v);
        else next.delete(k);
        if (k === "level") next.delete("minor");
        return next;
      },
      { replace: true }
    );

  useEffect(() => {
    api.pitchers().then(setPitchers).catch((e) => setError(e.message));
  }, [user]);

  // search / hand / role apply first, so the tab counts show what each tab would contain
  const base = useMemo(() => {
    if (!pitchers) return null;
    const q = query.trim().toLowerCase();
    return pitchers.filter(
      (p) =>
        (!throws || p.throws === throws) &&
        (!role || p.role === role) &&
        (!data || (data === "simulated") === (p.source === "simulated")) &&
        (!q || [p.name, p.team, p.hometown, p.affiliation].some((f) => f?.toLowerCase().includes(q)))
    );
  }, [pitchers, query, throws, role, data]);

  const groups = useMemo(() => {
    if (!base) return [];
    return LEVEL_GROUPS.map((g) => ({ ...g, count: base.filter(g.match).length })).filter(
      (g) => g.key !== "unset" || g.count > 0
    );
  }, [base]);

  const group = groups.find((g) => g.key === level) ?? LEVEL_GROUPS[0];

  const shown = useMemo(() => {
    if (!base) return null;
    return base
      .filter(group.match)
      .filter((p) => !minor || p.level === minor)
      .sort(compare(sort));
  }, [base, group, minor, sort]);

  const defs = defsByKey(statDefs);

  return (
    <>
      <header className="page-head">
        <div>
          <h2 className="page-title">Scout players</h2>
          <p className="muted">
            {group.blurb} Add anyone to your dugout to track them.
          </p>
        </div>
        <input
          className="search"
          type="search"
          placeholder="Search name, team, hometown or org"
          value={query}
          onChange={(e) => setParam("q", e.target.value)}
          aria-label="Search pitchers"
        />
      </header>

      {groups.length > 0 && (
        <LevelTabs groups={groups} value={group.key} onChange={(k) => setParam("level", k === "all" ? "" : k)} />
      )}

      <div className="filter-bar">
        {group.key === "minors" && (
          <Segmented
            label="Minor-league level"
            value={minor}
            onChange={(v) => setParam("minor", v)}
            options={[["", "All minors"], ...MINOR_LEVELS.map((l) => [l, LEVEL_LABEL[l]])]}
          />
        )}
        <Segmented label="Throws" value={throws} onChange={(v) => setParam("throws", v)} options={[["", "Both hands"], ["R", "RHP"], ["L", "LHP"]]} />
        <Segmented label="Role" value={role} onChange={(v) => setParam("role", v)} options={[["", "All roles"], ["SP", "Starters"], ["RP", "Relievers"]]} />
        <Segmented label="Data" value={data} onChange={(v) => setParam("data", v)} options={[["", "All data"], ["real", "Real"], ["simulated", "Simulated"]]} />
        <label className="sort">
          <span className="muted small">Sort</span>
          <select value={sort} onChange={(e) => setParam("sort", e.target.value === "name" ? "" : e.target.value)}>
            {Object.entries(SORTS).map(([k, s]) => (
              <option key={k} value={k}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        {shown && <span className="muted small result-count">{shown.length} pitcher{shown.length === 1 ? "" : "s"}</span>}
      </div>

      {error && <div className="error" role="alert">{error} — is the API running on port 8000?</div>}
      {!pitchers && !error && <p className="muted">Loading…</p>}
      {shown && shown.length === 0 && <p className="muted">No pitchers match these filters.</p>}

      {shown && statDefs.length > 0 && (
        <div className="card-grid">
          {shown.map((p) => (
            <BaseballCard
              key={p.id}
              pitcher={p}
              to={`/players/${p.id}`}
              badge={p.is_mine ? "Yours" : null}
              stats={[
                ...CARD_KEYS.map((k) => ({ def: defs[k], value: p[k] })),
                { def: defs.fb_velo, value: p.avg_fb_velo },
              ]}
            >
              <TrackButton
                pitcher={p}
                onChange={(tracked) =>
                  setPitchers((ps) => ps.map((x) => (x.id === p.id ? { ...x, is_tracked: tracked } : x)))
                }
              />
            </BaseballCard>
          ))}
        </div>
      )}
    </>
  );
}
