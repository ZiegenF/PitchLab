import { Link } from "react-router-dom";
import Avatar from "./Avatar";
import StatDelta from "./StatDelta";
import { LEVEL_LABEL, affiliationLabel, classLabel } from "../levels";
import { formatStat } from "../stats";

/**
 * A player as a baseball card: photo on a mowed-field background, team ribbon, role in a
 * home-plate badge, level and portal chips, name plate, and a strip of stats.
 *   stats: [{ def, value, recent }]  (recent optional, enables the trend arrow)
 */
export default function BaseballCard({ pitcher, stats = [], recentGames, to, badge, children }) {
  const photo = (
    <div className="bcard-photo">
      {pitcher.team && <span className="bcard-ribbon">{pitcher.team}</span>}
      <span className="bcard-plate" title={pitcher.role === "SP" ? "Starter" : "Reliever"}>
        {pitcher.role}
      </span>
      <Avatar name={pitcher.name} src={pitcher.photo_url} size={92} />
      {pitcher.level && <span className="bcard-level">{LEVEL_LABEL[pitcher.level]}</span>}
      {pitcher.in_portal && <span className="bcard-portal">⇄ In portal</span>}
    </div>
  );
  const sub = [`${pitcher.throws}HP`, classLabel(pitcher), pitcher.hometown].filter(Boolean).join(" · ");
  const aff = affiliationLabel(pitcher);

  return (
    <article className="bcard">
      {to ? <Link to={to} className="bcard-link" aria-label={`Open ${pitcher.name}`}>{photo}</Link> : photo}
      <div className="bcard-name">
        {to ? <Link to={to}>{pitcher.name}</Link> : pitcher.name}
        {badge && <span className="bcard-badge">{badge}</span>}
      </div>
      <div className="bcard-sub">{sub}</div>
      {aff && <div className="bcard-aff">{aff}</div>}
      {stats.length > 0 && (
        <dl className="bcard-stats">
          {stats.map(({ def, value, recent }) => (
            <div key={def.key} className="bcard-stat" title={def.description}>
              <dt>{def.label}</dt>
              <dd>{formatStat(def, value)}</dd>
              {recent !== undefined && (
                <StatDelta def={def} season={value} recent={recent} recentGames={recentGames} compact />
              )}
            </div>
          ))}
        </dl>
      )}
      {children && <div className="bcard-footer">{children}</div>}
    </article>
  );
}
