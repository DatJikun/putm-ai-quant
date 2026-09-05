export function CarSchematic() {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <figure className="rounded-xl bg-[#07090d] p-3 ring-1 ring-white/10">
        <svg viewBox="0 0 320 140" className="w-full" aria-label="Widok z boku bolidu">
          <text x="8" y="14" fill="#8b95a7" fontSize="8" fontFamily="ui-monospace">
            SIDE · ride height 25 / 32 mm
          </text>
          <line x1="12" y1="118" x2="308" y2="118" stroke="#3d4654" />
          <rect x="12" y="118" width="296" height="4" fill="#1b222c" />
          {/* ground effect gap */}
          <rect x="70" y="108" width="160" height="8" fill="#1a6b8a" opacity="0.45" />
          {/* floor */}
          <path d="M72 108 L88 108 L230 100 L248 92 L248 108 Z" fill="#2a3340" />
          {/* chassis */}
          <path d="M86 108 L102 70 L150 62 L210 66 L230 88 L230 108 Z" fill="#cfd6e0" />
          {/* hoop */}
          <path d="M168 62 L176 28 L188 62" fill="none" stroke="#f4c14d" strokeWidth="3" />
          {/* driver */}
          <circle cx="156" cy="50" r="8" fill="#9aa6b8" />
          {/* front wing */}
          <path d="M28 100 L70 96 L70 108 L28 110 Z" fill="#5ee0c0" />
          {/* rear wing */}
          <path d="M248 48 L292 44 L292 70 L248 74 Z" fill="#ff7a59" />
          <rect x="268" y="38" width="18" height="6" fill="#ff9a7a" />
          {/* wheels */}
          <circle cx="58" cy="112" r="16" fill="#11141a" stroke="#d0d6e0" />
          <circle cx="232" cy="112" r="16" fill="#11141a" stroke="#d0d6e0" />
          <text x="28" y="88" fill="#5ee0c0" fontSize="7">
            FW
          </text>
          <text x="256" y="36" fill="#ff7a59" fontSize="7">
            RW
          </text>
          <text x="118" y="132" fill="#6b7687" fontSize="7" fontFamily="ui-monospace">
            wb 1600 mm
          </text>
        </svg>
        <figcaption className="mt-1 px-1 text-xs text-muted-foreground">
          Zielony = przednie skrzydło, łosoś = tylne, teal = podłoga. Hoop w amberze — źródło brudnego powietrza.
        </figcaption>
      </figure>
      <figure className="rounded-xl bg-[#07090d] p-3 ring-1 ring-white/10">
        <svg viewBox="0 0 320 140" className="w-full" aria-label="Widok z góry bolidu">
          <text x="8" y="14" fill="#8b95a7" fontSize="8" fontFamily="ui-monospace">
            TOP · track 1200 mm · A 0.92 m²
          </text>
          {/* FW */}
          <rect x="18" y="36" width="36" height="68" rx="2" fill="#5ee0c0" />
          {/* nose */}
          <path d="M54 54 L86 48 L86 92 L54 86 Z" fill="#cfd6e0" />
          {/* body */}
          <rect x="86" y="46" width="140" height="48" rx="8" fill="#cfd6e0" />
          {/* cockpit hole */}
          <rect x="132" y="54" width="36" height="32" rx="6" fill="#07090d" />
          {/* RW */}
          <rect x="268" y="34" width="34" height="72" rx="2" fill="#ff7a59" />
          {/* wheels */}
          <rect x="70" y="18" width="28" height="18" rx="3" fill="#11141a" stroke="#d0d6e0" />
          <rect x="70" y="104" width="28" height="18" rx="3" fill="#11141a" stroke="#d0d6e0" />
          <rect x="214" y="18" width="28" height="18" rx="3" fill="#11141a" stroke="#d0d6e0" />
          <rect x="214" y="104" width="28" height="18" rx="3" fill="#11141a" stroke="#d0d6e0" />
          {/* stations */}
          {[40, 84, 118, 160, 204, 236, 270, 300].map((x, i) => (
            <g key={x}>
              <line
                x1={x}
                y1="16"
                x2={x}
                y2="124"
                stroke="#f4c14d"
                strokeDasharray="2 3"
                opacity="0.45"
              />
              <text x={x + 2} y="132" fill="#f4c14d" fontSize="6" fontFamily="ui-monospace">
                X{i + 1}
              </text>
            </g>
          ))}
        </svg>
        <figcaption className="mt-1 px-1 text-xs text-muted-foreground">
          Przerywane linie to hero stacje osi X, które agent dostaje zamiast wszystkich 60 płaszczyzn.
        </figcaption>
      </figure>
    </div>
  )
}
