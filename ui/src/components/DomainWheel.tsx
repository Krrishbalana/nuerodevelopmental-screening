import type { WheelSlice } from "../types";

const PALETTE = ["#b4475a", "#d9822b", "#d9a62e", "#5aa469", "#2a9d8f", "#4ea8de", "#3a5ba0", "#7b4fb5", "#8a5a3c", "#c06c84", "#6f7f2e", "#5c6474"];
const SIZE = 520;
const C = SIZE / 2;
const R = 170;
const PAD_X = 150;
const PAD_Y = 40;

const STATUS = {
  concern: { label: "Concern", cls: "flagged" },
  some: { label: "Some signs", cls: "reported" },
  clear: { label: "No signs", cls: "not_flagged" },
  not_assessed: { label: "Not checked", cls: "not_assessed" },
} as const;

function polar(r: number, deg: number) {
  const a = (deg * Math.PI) / 180;
  return { x: C + r * Math.cos(a), y: C + r * Math.sin(a) };
}

function wedge(r: number, a0: number, a1: number) {
  const p0 = polar(r, a0);
  const p1 = polar(r, a1);
  return `M ${C} ${C} L ${p0.x} ${p0.y} A ${r} ${r} 0 0 1 ${p1.x} ${p1.y} Z`;
}

function labelLines(label: string): string[] {
  const lines = [""];
  for (const w of label.split(" ")) {
    const cur = lines[lines.length - 1];
    if (cur && (cur + " " + w).length > 14 && lines.length < 2) lines.push(w);
    else lines[lines.length - 1] = cur ? `${cur} ${w}` : w;
  }
  return lines;
}

/**
 * Development profile across all areas, not just autism. Slice size = share of the signs checked in
 * that area that were reported by the parent or seen by the camera. Striped = not checked for this
 * child (the questions adapt, so a child is only asked about what's relevant).
 */
export function DomainWheel({
  slices,
  detailed = false,
  label = "Development profile",
  codesLabel = "Domains",
}: {
  slices: WheelSlice[];
  detailed?: boolean;
  label?: string;
  codesLabel?: string;
}) {
  const step = 360 / slices.length;
  return (
    <div className="profile">
      <svg
        viewBox={`${-PAD_X} ${-PAD_Y} ${SIZE + 2 * PAD_X} ${SIZE + 2 * PAD_Y}`}
        className="profile-svg"
        role="img"
        aria-label={label}
      >
        <defs>
          <pattern id="dw-hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="7" stroke="#cfd5df" strokeWidth="2" />
          </pattern>
        </defs>
        <circle cx={C} cy={C} r={R} fill="#f7f8fb" stroke="#1d2433" strokeWidth="2" />
        {[0.25, 0.5, 0.75].map((f) => (
          <circle key={f} cx={C} cy={C} r={R * f} fill="none" stroke="#dfe3ea" strokeDasharray="2 4" />
        ))}
        {slices.map((s, i) => {
          const a0 = -90 + i * step + 0.6;
          const a1 = -90 + (i + 1) * step - 0.6;
          const mid = (a0 + a1) / 2;
          const label = polar(R + 26, mid);
          const anchor = Math.abs(label.x - C) < 12 ? "middle" : label.x > C ? "start" : "end";
          return (
            <g key={s.key}>
              {s.value === null ? (
                <path d={wedge(R, a0, a1)} fill="url(#dw-hatch)" opacity={0.7} />
              ) : (
                <path
                  d={wedge(Math.max(4, R * s.value), a0, a1)}
                  fill={PALETTE[i % PALETTE.length]}
                  opacity={0.9}
                  stroke={s.status === "concern" ? "#1d2433" : "none"}
                  strokeWidth={s.status === "concern" ? 2.5 : 0}
                />
              )}
              <text x={label.x} y={label.y} textAnchor={anchor} className={s.value === null ? "profile-label dim" : "profile-label"}>
                {labelLines(s.label).map((line, k, all) => (
                  <tspan key={k} x={label.x} dy={k === 0 ? `${0.35 - (all.length - 1) * 0.55}em` : "1.1em"}>
                    {line}
                  </tspan>
                ))}
              </text>
            </g>
          );
        })}
        {slices.map((_, i) => {
          const p = polar(R, -90 + i * step);
          return <line key={i} x1={C} y1={C} x2={p.x} y2={p.y} stroke="#1d2433" strokeWidth="1.2" />;
        })}
        <circle cx={C} cy={C} r={R} fill="none" stroke="#1d2433" strokeWidth="2" />
      </svg>

      <ul className="profile-legend">
        {slices
          .filter((s) => detailed || s.value !== null)
          .map((s) => (
            <li key={s.key}>
              <span
                className="swatch"
                style={
                  s.value === null
                    ? { background: "repeating-linear-gradient(45deg, #cfd5df 0 2px, #fff 2px 5px)" }
                    : { background: PALETTE[slices.indexOf(s) % PALETTE.length] }
                }
              />
              <div>
                <b>{s.label}</b> <span className={`pill ${STATUS[s.status].cls}`}>{STATUS[s.status].label}</span>
                {s.value !== null && (
                  <span className="small muted">
                    {" "}
                    {s.signs.length} of {s.checked} checked
                  </span>
                )}
                {s.signs.length > 0 && <div className="small muted">{s.signs.join(" · ")}</div>}
                {detailed && <div className="small muted">{codesLabel}: {s.domains.join(", ")}</div>}
              </div>
            </li>
          ))}
        {!detailed && slices.some((s) => s.value === null) && (
          <li className="muted small">
            Not checked this time: {slices.filter((s) => s.value === null).map((s) => s.label).join(", ")}.
          </li>
        )}
      </ul>
    </div>
  );
}
