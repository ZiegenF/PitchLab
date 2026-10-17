const initials = (name = "") =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("");

export default function Avatar({ name, src, size = 40 }) {
  const style = { width: size, height: size, fontSize: size * 0.38 };
  return src ? (
    <img className="avatar" src={src} alt={name} style={style} />
  ) : (
    <span className="avatar avatar-initials" style={style} aria-hidden="true">
      {initials(name)}
    </span>
  );
}
