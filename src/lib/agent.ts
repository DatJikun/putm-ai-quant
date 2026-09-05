import { reynolds } from "./demo-case"
import type {
  AeroKpis,
  AgentReview,
  CadModel,
  FluentCase,
  PostImage,
} from "./types"

const FS_RANGES = {
  Cl: { lo: -5.2, hi: -2.4, sweet: [-4.2, -3.0] },
  Cd: { lo: 0.85, hi: 1.85, sweet: [1.1, 1.5] },
  LOverD: { lo: 1.8, hi: 3.6, sweet: [2.4, 3.2] },
  frontBalance: { lo: 38, hi: 52, sweet: [44, 48] },
}

function clampScore(n: number) {
  return Math.max(0, Math.min(100, Math.round(n)))
}

function inSweet(v: number, sweet: number[], range: { lo: number; hi: number }) {
  if (v >= sweet[0] && v <= sweet[1]) return 92
  if (v >= range.lo && v <= range.hi) return 72
  return 38
}

export function evaluateCase(
  fluent: FluentCase,
  kpis: AeroKpis,
  cad: CadModel,
  images: PostImage[],
): AgentReview {
  const heroes = images.filter((i) => i.hero)
  const byAxis = {
    full: images.filter((i) => i.axis === "full").length,
    x: images.filter((i) => i.axis === "x").length,
    y: images.filter((i) => i.axis === "y").length,
    z: images.filter((i) => i.axis === "z").length,
  }

  const continuityOk = fluent.residuals.continuity < 1e-4
  const yPlusSetupMismatch =
    fluent.wallTreatment.includes("y+ ≈ 1") && fluent.yPlusWings.avg > 5

  const zbieznosc = clampScore(
    continuityOk ? 86 : 64 - Math.log10(fluent.residuals.continuity) * 4,
  )
  const siatka = clampScore(
    90 - (yPlusSetupMismatch ? 28 : 0) - (fluent.cellsM < 12 ? 15 : 0),
  )
  const wydajnosc = inSweet(kpis.LOverD, FS_RANGES.LOverD.sweet, FS_RANGES.LOverD)
  const balanse = inSweet(
    kpis.frontBalancePct,
    FS_RANGES.frontBalance.sweet,
    FS_RANGES.frontBalance,
  )
  const pokrycieWizualne = clampScore(
    40 +
      (byAxis.x > 400 ? 15 : 8) +
      (byAxis.y > 200 ? 12 : 5) +
      (byAxis.z > 300 ? 12 : 5) +
      (heroes.length >= 12 ? 15 : 6),
  )

  const review: AgentReview = {
    verdict: "warunkowo-akceptowalne",
    summary: "",
    scores: { zbieznosc, siatka, wydajnosc, balanse, pokrycieWizualne },
    findings: [],
    questions: [],
    nextRuns: [],
  }

  if (!continuityOk) {
    review.findings.push({
      id: "resid-cont",
      severity: "issue",
      title: "Continuity nie zeszło poniżej 1e-4",
      evidence: `Po ${fluent.iterations} iteracjach residual continuity = ${fluent.residuals.continuity.toExponential(2)}. Siły mogą jeszcze dryfować o 1–3%.`,
      recommendation:
        "Doiterować albo włączyć averaging ostatnich 200 iteracji i podać min/max Cl, Cd. Nie porównuj geometrii na trzecim miejscu po przecinku.",
    })
  }

  if (yPlusSetupMismatch) {
    review.findings.push({
      id: "yplus-wings",
      severity: "issue",
      title: "y+ na skrzydłach nie zgadza się z low-Re SST",
      evidence: `Setup deklaruje y+ ≈ 1, a na skrzydłach y+ średnie = ${fluent.yPlusWings.avg} (max ${fluent.yPlusWings.max}). Podłoga jest bliżej celu (avg ${fluent.yPlusFloor.avg}).`,
      recommendation:
        "Zagęścić pryzmę na płatach i klapach albo przełączyć warstwę przyścienną na wall functions i nie mieszać obu podejść w jednym raporcie.",
    })
  }

  if (kpis.frontBalancePct < FS_RANGES.frontBalance.sweet[0]) {
    review.findings.push({
      id: "balance-rear",
      severity: "watch",
      title: `Balans ${kpis.frontBalancePct}% z przodu — auto tyłociężkie aero`,
      evidence: `Front wing ${kpis.components[0].Cl} Cl vs rear wing ${kpis.components[2].Cl} Cl. Przy ride height ${cad.rideHeightFrontMm}/${cad.rideHeightRearMm} mm i rake ${cad.rakeDeg}°.`,
      recommendation:
        "Albo dodać load na FW (kąt / Gurney / mniejszy ride height przodu), albo zdjąć górny płat RW. Sprawdź yaw 3–6°, bo FS na slalomie żyje z yaw.",
    })
  }

  const wheels = kpis.components.find((c) => c.name.startsWith("Wheels"))
  if (wheels && wheels.shareDragPct >= 25) {
    review.findings.push({
      id: "wheel-drag",
      severity: "watch",
      title: "Koła zjadają za dużo drag",
      evidence: `${wheels.shareDragPct}% całego Cd. W katalogu X/vorticity przy osi przedniej widać mocny wir; Z/Cp total na podłodze powinien pokazać, czy ten ślad wchodzi w dyfuzor.`,
      recommendation:
        "Hero klatki: X≈0.70 m vorticity + Z≈0.12 m Cp total. Jeśli ślad idzie pod podłogę — najpierw bargeboard / wheel wake management, nie kolejny płat RW.",
    })
  }

  review.findings.push({
    id: "rw-dirty-air",
    severity: "watch",
    title: "Tylne skrzydło prawdopodobnie w brudnym powietrzu hoopa",
    evidence:
      "Widok iso-rear |V| + stacje X za kokpitem (Cp total). Hoop i kask zrzucają niski Cp total na górny płat. To typowy koszt FS, ale 24% downforce z RW przy 22% drag sugeruje, że płat pracuje mniej czysto niż FW.",
    recommendation:
      "Porównać Cp na głównym płacie RW z izolowanym skrzydłem. Jeśli ssanie na 30–60% cięciwy jest płaskie — podnieść RW albo zwęzić kask/hoop fairing.",
  })

  if (kpis.LOverD >= 2.4) {
    review.findings.push({
      id: "lod-ok",
      severity: "info",
      title: `L/D = ${kpis.LOverD.toFixed(2)} — w normie mocnego paczka FS`,
      evidence: `Cl ${kpis.Cl}, Cd ${kpis.Cd}, Re ≈ ${(reynolds() / 1e6).toFixed(2)}e6 na rozstawie osi. Downforce ${kpis.downforceN.toFixed(0)} N / drag ${kpis.dragN.toFixed(0)} N przy ${fluent.speedMs} m/s.`,
      recommendation:
        "Traktuj L/D jako KPI sezonu, ale decyzje geometryczne podejmuj na komponentach i yaw, nie na jednej liczbie z yaw 0.",
    })
  }

  const missingHero =
    heroes.filter((h) => h.axis === "x").length < 6 ||
    !heroes.some((h) => h.axis === "y") ||
    !heroes.some((h) => h.axis === "z")
  if (missingHero) {
    review.findings.push({
      id: "coverage",
      severity: "blocker",
      title: "Brakuje hero klatek na jednej z osi",
      evidence: `Hero: ${heroes.length}. X/Y/Z muszą mieć reprezentację, inaczej VLM zgaduje.`,
      recommendation: "Nie wysyłaj packa dopóki selector nie wybierze stacji na FW, osiach, dyfuzorze i wake.",
    })
  } else {
    review.findings.push({
      id: "coverage-ok",
      severity: "info",
      title: `${images.length} klatek zredukowane do ${heroes.length} hero`,
      evidence: `Pokrycie osi: full ${byAxis.full}, X ${byAxis.x}, Y ${byAxis.y}, Z ${byAxis.z}. Agent dostaje stacje na skrzydłach, kołach, podłodze, hoopie i śladzie — nie 1500 PNG.`,
      recommendation:
        "Do VLM dokładaj maksymalnie te hero + 4 klatki, o które agent sam poprosi (tool call), nigdy cały dump.",
    })
  }

  review.questions = [
    "Czy siatka jest half-model z symmetry, czy full-car? Cs≈0.01 sugeruje full albo numeryczny szum.",
    "Jaki rolling road i RPM kół? Drag kół 27% mocno zależy od rotacji.",
    "Czy jest case yaw 3° i 6° na tej samej geometrii? Balans 41% przy yaw 0 może się odwrócić.",
    "Jakie Cl/Cd z tunelu albo z poprzedniego bolidu na tym samym setupie?",
  ]

  review.nextRuns = [
    "Mesh refinement na płatach do y+ < 2, ten sam setup — delta Cl, Cd, y+.",
    "Yaw 0 / 3 / 6° sweep, te same hero stacje.",
    "Front ride height 20 vs 25 mm — czy podłoga nie stalluje.",
    "Off: górny płat RW vs on: wheel wake strake — który daje lepszy L/D przy balansie 45%.",
  ]

  const issues = review.findings.filter((f) => f.severity === "issue").length
  const blockers = review.findings.filter((f) => f.severity === "blocker").length
  if (blockers) review.verdict = "nieufne"
  else if (issues >= 2) review.verdict = "do-poprawy"
  else if (issues >= 1 || review.findings.some((f) => f.severity === "watch"))
    review.verdict = "warunkowo-akceptowalne"
  else review.verdict = "akceptowalne"

  review.summary = `Case ${fluent.name}: L/D ${kpis.LOverD.toFixed(2)}, balans ${kpis.frontBalancePct}% z przodu, ${heroes.length} hero z ${images.length} klatek. y+ na skrzydłach i continuity ograniczają pewność sił — ${review.verdict === "akceptowalne" ? "można porównywać geometrie" : "nie porównuj geometrii na trzecim miejscu po przecinku, zanim to posprzątasz"}. Agent nie powinien oglądać surowych .cas/.dat, tylko ten pack.`

  return review
}

export const VERDICT_LABEL: Record<AgentReview["verdict"], string> = {
  akceptowalne: "Akceptowalne",
  "warunkowo-akceptowalne": "Warunkowo akceptowalne",
  "do-poprawy": "Do poprawy zanim porównasz geometrie",
  nieufne: "Nieufne — pack niekompletny albo fizyka rozjechana",
}
