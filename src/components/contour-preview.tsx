import type { Axis, FieldId } from "@/lib/types"

const TURBO = [
  "#30123b",
  "#3b2c5a",
  "#414287",
  "#3b6fb6",
  "#2a9bd3",
  "#1ec9b6",
  "#5ae66a",
  "#c4ef34",
  "#fbb931",
  "#f36513",
  "#d93806",
]

function hash(s: string) {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

function colorAt(t: number) {
  const x = Math.max(0, Math.min(0.999, t)) * (TURBO.length - 1)
  return TURBO[Math.floor(x)]
}

function carPath(axis: Axis) {
  if (axis === "y") {
    // side silhouette
    return "M18 78 L28 78 L34 62 L52 58 L70 70 L118 70 L138 48 L162 44 L178 52 L178 78 L170 78 L162 88 L148 88 L140 78 L70 78 L62 88 L48 88 L40 78 Z"
  }
  if (axis === "x") {
    // rear/front section-ish
    return "M70 88 L80 40 L120 40 L130 88 L118 88 L112 70 L88 70 L82 88 Z M40 88 L48 62 L62 88 Z M138 88 L152 62 L160 88 Z"
  }
  if (axis === "z") {
    // top
    return "M40 48 L70 40 L130 40 L160 48 L168 58 L160 70 L130 78 L70 78 L40 70 L32 58 Z"
  }
  return "M24 70 L36 52 L58 48 L78 62 L130 62 L148 40 L172 38 L186 50 L186 78 L176 78 L166 90 L150 90 L140 78 L78 78 L68 90 L52 90 L42 78 Z"
}

export function ContourPreview({
  id,
  axis,
  field,
  stationM,
  className,
}: {
  id: string
  axis: Axis
  field: FieldId
  stationM: number | null
  className?: string
}) {
  const seed = hash(id)
  const blobs = Array.from({ length: 7 }, (_, i) => {
    const n = hash(`${id}-${i}`)
    return {
      cx: 20 + (n % 160),
      cy: 18 + ((n >> 8) % 80),
      rx: 18 + ((n >> 16) % 50),
      ry: 12 + ((n >> 24) % 36),
      t: ((seed >> (i * 3)) & 255) / 255,
    }
  })

  const high = field === "cpt" || field === "vort" || field === "tke"
  const title =
    stationM == null
      ? `${field} · ${axis}`
      : `${field} · ${axis}=${stationM.toFixed(2)} m`

  return (
    <svg
      viewBox="0 0 200 120"
      className={className}
      role="img"
      aria-label={title}
    >
      <defs>
        <linearGradient id={`bg-${id}`} x1="0" x2="1">
          {TURBO.map((c, i) => (
            <stop
              key={c + i}
              offset={`${(i / (TURBO.length - 1)) * 100}%`}
              stopColor={c}
            />
          ))}
        </linearGradient>
      </defs>
      <rect width="200" height="120" fill="#07090d" />
      <rect
        x="0"
        y="8"
        width="200"
        height="96"
        fill={high ? "#1a1144" : "#0b1c33"}
      />
      {blobs.map((b, i) => (
        <ellipse
          key={i}
          cx={b.cx}
          cy={b.cy}
          rx={b.rx}
          ry={b.ry}
          fill={colorAt(b.t)}
          opacity={0.55}
        />
      ))}
      <path d={carPath(axis)} fill="#0a0c10" opacity="0.72" />
      <path
        d={carPath(axis)}
        fill="none"
        stroke="#e8edf5"
        strokeWidth="0.7"
        opacity="0.85"
      />
      {axis !== "full" && (
        <line
          x1={axis === "x" ? 100 : 12}
          y1={axis === "z" ? 58 : 12}
          x2={axis === "x" ? 100 : 188}
          y2={axis === "z" ? 58 : 104}
          stroke="#f4c14d"
          strokeDasharray="3 3"
          strokeWidth="0.6"
          opacity="0.7"
        />
      )}
      <rect x="186" y="14" width="8" height="80" fill={`url(#bg-${id})`} />
      <text x="6" y="10" fill="#9aa6b8" fontSize="5" fontFamily="ui-monospace">
        {title}
      </text>
      <text x="6" y="116" fill="#6b7687" fontSize="4.5" fontFamily="ui-monospace">
        demo contour · nie jest to prawdziwy Fluent
      </text>
    </svg>
  )
}
