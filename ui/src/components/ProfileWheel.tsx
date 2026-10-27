import type { ProfileArea } from "../types";

// One colour per area, in wheel order.
const PALETTE = ["#b23a48", "#e07a2e", "#d9a62e", "#5aa469", "#2a9d8f", "#4ea8de", "#3a5ba0", "#7b4fb5", "#c06c84", "#8d6e63"];

const SIZE = 520;
const C = SIZE / 2;
const R = 170;
const PAD_X = 150; // room for labels left and right of the wheel
const PAD_Y = 40;

/** Up to two lines of about 14 characters. */
function labelLines(label: string): string[] {
  const words = label.split(" ");
  const lines = [""];
  for (const w of words) {
    const cur = lines[lines.length - 1];
    if (cur && (cur + " " + w).length > 14 && lines.length < 2) lines.push(w);
    else lines[lines.length - 1] = cur ? `${cur} ${w}` : w;
  }
  return lines;
}

function polar(r: number, deg: number) {
  const a = (deg * Math.PI) / 180;
  return { x: C + r * Math.cos(a), y: C + r * Math.sin(a) };
}

function wedge(r: number, a0: number, a1: number) {
  const p0 = polar(r, a0);
  const p1 = polar(r, a1);
  return `M ${C} ${C} L ${p0.x} ${p0.y} A ${r} ${r} 0 0 1 ${p1.x} ${p1.y} Z`;
}

function arc(r: number, a0: number, a1: number) {
  const p0 = polar(r, a0);
  const p1 = polar(r, a1);
  return `M ${p0.x} ${p0.y} A ${r} ${r} 0 0 1 ${p1.x} ${p1.y}`;
}

const STATUS_TEXT: Record<string, string> = {
  flagged: "Pattern seen",
  not_flagged: "Below cut-off",
  reported: "Reported",
  insufficient: "Not measured",
  not_assessed: "Not assessed",
};

/**
 * Radial development profile. Each slice is a separate area; its size is how much of the
 * autism-linked pattern this session showed (0 at the centre, 100% at the rim). Dashed arcs are
 * published cut-offs; ticks are published group averages; hatched slices weren't assessed.
 */
export function ProfileWheel({ areas, detailed = false }: { areas: ProfileArea[]; detailed?: boolean }) {
  const step = 360 / areas.length;
  const gap = 1.2;

  return (
    <div className="profile">
      <svg
        viewBox={`${-PAD_X} ${-PAD_Y} ${SIZE + 2 * PAD_X} ${SIZE + 2 * PAD_Y}`}
        className="profile-svg"
        role="img"
        aria-label="Development profile"
      >
        <defs>
          <pattern id="hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="7" stroke="#cfd5df" strokeWidth="2" />
          </pattern>
        </defs>
        <circle cx={C} cy={C} r={R} fill="#f7f8fb" stroke="#1d2433" strokeWidth="2" />
        {[0.25, 0.5, 0.75].map((f) => (
          <circle key={f} cx={C} cy={C} r={R * f} fill="none" stroke="#dfe3ea" strokeDasharray="2 4" />
        ))}

        {areas.map((a, i) => {
          const a0 = -90 + i * step + gap / 2;
          const a1 = -90 + (i + 1) * step - gap / 2;
          const mid = (a0 + a1) / 2;
          const color = PALETTE[i % PALETTE.length];
          const label = polar(R + 26, mid);
          const anchor = Math.abs(label.x - C) < 12 ? "middle" : label.x > C ? "start" : "end";
          return (
            <g key={a.key}>
              {a.status === "not_assessed" || a.value === null ? (
                <path d={wedge(R, a0, a1)} fill="url(#hatch)" opacity={a.status === "insufficient" ? 0.9 : 0.6} />
              ) : (
                <path
                  d={wedge(Math.max(3, R * a.value), a0, a1)}
                  fill={color}
                  opacity={a.tier === "B" ? 0.5 : 0.92}
                  stroke={a.status === "flagged" ? "#1d2433" : "none"}
                  strokeWidth={a.status === "flagged" ? 2.5 : 0}
                />
              )}
              {a.cutoff !== null && (
                <path d={arc(R * a.cutoff, a0, a1)} fill="none" stroke="#1d2433" strokeWidth="2.5" strokeDasharray="5 3" />
              )}
              {a.markers.map((m) => {
                const p0 = polar(R * m.value, mid - step * 0.18);
                const p1 = polar(R * m.value, mid + step * 0.18);
                return <line key={m.label} x1={p0.x} y1={p0.y} x2={p1.x} y2={p1.y} stroke="#1d2433" strokeWidth="2" />;
              })}
              <text x={label.x} y={label.y} textAnchor={anchor} className="profile-label">
                {labelLines(a.label).map((line, k, all) => (
                  <tspan key={k} x={label.x} dy={k === 0 ? `${0.35 - (all.length - 1) * 0.55}em` : "1.1em"}>
                    {line}
                  </tspan>
                ))}
              </text>
            </g>
          );
        })}
        {/* slice dividers */}
        {areas.map((_, i) => {
          const p = polar(R, -90 + i * step);
          return <line key={i} x1={C} y1={C} x2={p.x} y2={p.y} stroke="#1d2433" strokeWidth="1.5" />;
        })}
        <circle cx={C} cy={C} r={R} fill="none" stroke="#1d2433" strokeWidth="2" />
      </svg>

      <ul className="profile-legend">
        {areas.map((a, i) => (
          <li key={a.key} className={a.status === "not_assessed" ? "muted" : undefined}>
            <span
              className="swatch"
              style={
                a.status === "not_assessed" || a.value === null
                  ? { background: "repeating-linear-gradient(45deg, #cfd5df 0 2px, #fff 2px 5px)" }
                  : { background: PALETTE[i % PALETTE.length], opacity: a.tier === "B" ? 0.5 : 1 }
              }
            />
            <div>
              <b>{a.label}</b>{" "}
              <span className={`pill ${a.status}`}>{STATUS_TEXT[a.status] ?? a.status}</span>
              {a.value !== null && <span className="small"> {Math.round(a.value * 100)}%</span>}
              <div className="small muted">
                {a.measured}
                {a.cutoff_label && ` · cut-off: ${a.cutoff_label}`}
                {a.markers.length > 0 && ` · published averages: ${a.markers.map((m) => m.label).join(", ")}`}
              </div>
              {detailed && a.tier && <div className="small muted">Tier {a.tier}</div>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
