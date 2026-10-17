// A baseball: white ball, two seams, red stitches crossing each seam.
const RED = "#c41e3a";
const STITCH_YS = [7, 10, 13, 16, 19, 22, 25];

// Each seam bows toward the center: x at the middle (y=16) is 5px in from its ends.
// The quadratic curve below traces exactly this parabola (control x = 2*mid - end).
const seamX = (y, side) => {
  const t = (y - 16) / 12;
  return side === "left" ? 14.5 - 5 * t * t : 17.5 + 5 * t * t;
};

export default function Logo({ size = 32 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" className="logo">
      <circle cx="16" cy="16" r="14.5" fill="#fbf8ef" stroke="#d8d2c0" />
      {["left", "right"].map((side) => (
        <g key={side} stroke={RED} fill="none" strokeLinecap="round">
          <path
            strokeWidth="1.3"
            d={`M${seamX(4, side)} 4 Q${side === "left" ? 19.5 : 12.5} 16 ${seamX(28, side)} 28`}
          />
          {STITCH_YS.map((y) => (
            <path key={y} strokeWidth="1" d={`M${seamX(y, side) - 1.3} ${y - 0.7}l2.6 1.4`} />
          ))}
        </g>
      ))}
    </svg>
  );
}
