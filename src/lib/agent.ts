import type {
  AeroKpis,
  AgentReview,
  CadModel,
  FluentCase,
  PostImage,
  ReviewFinding,
} from "./types"

const FS_RANGES = {
  Cl: { lo: -5.2, hi: -2.4, sweet: [-4.2, -3.0] },
  Cd: { lo: 0.85, hi: 1.85, sweet: [1.1, 1.5] },
  LOverD: { lo: 1.8, hi: 3.6, sweet: [2.4, 3.2] },
  frontBalance: { lo: 38, hi: 52, sweet: [44, 48] },
}

export type ReviewDevice = {
  id: string
  role?: string
  group?: string
}

function clampScore(n: number) {
  return Math.max(0, Math.min(100, Math.round(n)))
}

function inSweet(
  v: number | null,
  sweet: number[],
  range: { lo: number; hi: number },
) {
  if (v == null || Number.isNaN(v)) return null
  if (v >= sweet[0] && v <= sweet[1]) return 92
  if (v >= range.lo && v <= range.hi) return 72
  return 38
}

function caseReynolds(fluent: FluentCase) {
  if (
    fluent.referenceLengthM == null ||
    !fluent.speedMs ||
    !fluent.rho ||
    !fluent.mu
  ) {
    return null
  }
  return (fluent.rho * fluent.speedMs * fluent.referenceLengthM) / fluent.mu
}

function componentByName(kpis: AeroKpis, pattern: RegExp) {
  return kpis.components.find((item) => pattern.test(item.name))
}

export function evaluateCase(
  fluent: FluentCase,
  kpis: AeroKpis,
  cad: CadModel,
  images: PostImage[],
  devices: ReviewDevice[] = [],
): AgentReview {
  const heroes = images.filter((i) => i.hero)
  const byAxis = {
    full: images.filter((i) => i.axis === "full").length,
    x: images.filter((i) => i.axis === "x").length,
    y: images.filter((i) => i.axis === "y").length,
    z: images.filter((i) => i.axis === "z").length,
  }

  const continuity = fluent.residuals.continuity
  const continuityOk = continuity != null && continuity < 1e-4
  const yPlusAvg = fluent.yPlusWings?.avg ?? null
  const yPlusSetupMismatch =
    yPlusAvg != null &&
    fluent.wallTreatment.includes("y+ ≈ 1") &&
    yPlusAvg > 5

  const zbieznosc =
    continuity == null || continuity <= 0
      ? null
      : clampScore(continuityOk ? 86 : 64 - Math.log10(continuity) * 4)

  let siatka: number | null = null
  if (fluent.cellsM != null || yPlusAvg != null || fluent.minOrthogonalQuality != null) {
    let score = 88
    if (yPlusSetupMismatch) score -= 28
    if (fluent.cellsM != null && fluent.cellsM < 12) score -= 15
    if (fluent.minOrthogonalQuality != null && fluent.minOrthogonalQuality < 0.05) score -= 20
    if (fluent.minOrthogonalQuality != null && fluent.minOrthogonalQuality < 0.01) score -= 15
    siatka = clampScore(score)
  }

  const wydajnosc = inSweet(kpis.LOverD, FS_RANGES.LOverD.sweet, FS_RANGES.LOverD)
  const balanse = inSweet(
    kpis.frontBalancePct,
    FS_RANGES.frontBalance.sweet,
    FS_RANGES.frontBalance,
  )
  const pokrycieWizualne =
    images.length === 0
      ? null
      : clampScore(
          40 +
            (byAxis.x > 400 ? 15 : byAxis.x > 0 ? 8 : 0) +
            (byAxis.y > 200 ? 12 : byAxis.y > 0 ? 5 : 0) +
            (byAxis.z > 300 ? 12 : byAxis.z > 0 ? 5 : 0) +
            (heroes.length >= 12 ? 15 : heroes.length > 0 ? 6 : 0),
        )

  const findings: ReviewFinding[] = []

  if (kpis.Cd == null || kpis.Cl == null) {
    findings.push({
      id: "kpi-missing",
      severity: "blocker",
      title: "Brak Cd albo Cl z solvera",
      evidence:
        "Pack nie ma zweryfikowanego współczynnika. Ocena L/D i balansu jest wstrzymana.",
      recommendation:
        "Dopnij monitor cx/cz i wektor siły z .cas. Nie podstawiaj liczb z innego case'a.",
    })
  }

  if (continuity == null) {
    findings.push({
      id: "resid-missing",
      severity: "issue",
      title: "Brak residuali w packu",
      evidence:
        "Transcript nie zawiera tabeli iter / continuity albo ingest jej nie znalazł. Zbieżność nie jest oceniona.",
      recommendation:
        "Zostaw w .trn tabelę residuali z nagłówkiem continuity x-velocity y-velocity z-velocity.",
    })
  } else if (!continuityOk) {
    findings.push({
      id: "resid-cont",
      severity: "issue",
      title: "Continuity nie zeszło poniżej 1e-4",
      evidence: `Po ${fluent.iterations ?? "nieznanej liczbie"} iteracjach residual continuity = ${continuity.toExponential(2)}. Siły mogą jeszcze dryfować o 1–3%.`,
      recommendation:
        "Doiterować albo włączyć averaging ostatnich 200 iteracji i podać min/max Cl, Cd. Nie porównuj geometrii na trzecim miejscu po przecinku.",
    })
  }

  if (fluent.yPlusWings == null && fluent.yPlusFloor == null) {
    findings.push({
      id: "yplus-missing",
      severity: "watch",
      title: "Brak y+ w packu",
      evidence: "Transcript nie ma statystyk y-plus per strefa. Warstwa przyścienna nie wchodzi do oceny.",
      recommendation:
        "Zrzuć area-weighted average / min / max of y-plus na surface_fw, surface_rw i surface_ut.",
    })
  } else if (yPlusSetupMismatch && fluent.yPlusWings) {
    findings.push({
      id: "yplus-wings",
      severity: "issue",
      title: "y+ na skrzydłach nie zgadza się z low-Re SST",
      evidence: `Setup deklaruje y+ ≈ 1, a na skrzydłach y+ średnie = ${fluent.yPlusWings.avg} (max ${fluent.yPlusWings.max ?? "brak"}). Podłoga: avg ${fluent.yPlusFloor?.avg ?? "brak"}.`,
      recommendation:
        "Zagęścić pryzmę na płatach i klapach albo przełączyć warstwę przyścienną na wall functions i nie mieszać obu podejść w jednym raporcie.",
    })
  }

  if (fluent.minOrthogonalQuality != null && fluent.minOrthogonalQuality < 0.01) {
    findings.push({
      id: "ortho-low",
      severity: "issue",
      title: "Minimalna jakość ortogonalna poniżej 0.01",
      evidence: `min orthogonal quality = ${fluent.minOrthogonalQuality}.`,
      recommendation: "Popraw siatkę zanim porównasz współczynniki między geometriami.",
    })
  }

  const rw = componentByName(kpis, /rear wing/i)
  const crashes = fluent.solverCrashes ?? []
  if (crashes.length > 0) {
    const allCrashed = crashes.length === (fluent.solverSessionCount ?? crashes.length)
    findings.push({
      id: "solver-crash",
      severity: allCrashed ? "issue" : "watch",
      title: allCrashed
        ? "Każdy transcript w folderze kończy się awarią Fluenta"
        : `Fluent padł w ${crashes.length} z ${fluent.solverSessionCount} sesji`,
      evidence: crashes.join("; "),
      recommendation: allCrashed
        ? "Monitory w folderze mogą pochodzić z innej sesji, po której nie ma transcriptu. Potwierdź, z którego przebiegu są liczby, zanim porównasz geometrie."
        : "Sprawdź, czy monitory pochodzą z sesji bez awarii.",
    })
  }

  const axles = kpis.balanceAxles
  const axleText =
    axles && axles.front != null && axles.rear != null
      ? `Docisk na osi przedniej ${axles.front.toFixed(3)}, na tylnej ${axles.rear.toFixed(3)} (współczynniki, z cm i osi kół).`
      : "Balans z monitora cm i osi kół."
  const ride =
    cad.rideHeightFrontMm != null && cad.rideHeightRearMm != null
      ? ` Ride height ${cad.rideHeightFrontMm}/${cad.rideHeightRearMm} mm, rake ${cad.rakeDeg ?? "brak"}°.`
      : ""
  if (
    kpis.frontBalancePct != null &&
    kpis.frontBalancePct < FS_RANGES.frontBalance.sweet[0]
  ) {
    findings.push({
      id: "balance-rear",
      severity: "watch",
      title: `Balans ${kpis.frontBalancePct}% z przodu — auto tyłociężkie aero`,
      evidence: `${axleText}${ride}`,
      recommendation:
        "Albo dodać load na FW (kąt / Gurney / mniejszy ride height przodu), albo zdjąć górny płat RW. Ten case jest na yaw 0 — balans w slalomie może wyglądać inaczej.",
    })
  } else if (
    kpis.frontBalancePct != null &&
    kpis.frontBalancePct > FS_RANGES.frontBalance.sweet[1]
  ) {
    findings.push({
      id: "balance-front",
      severity: "watch",
      title: `Balans ${kpis.frontBalancePct}% z przodu — auto przodociężkie aero`,
      evidence: `${axleText}${ride}`,
      recommendation:
        "Przesunąć docisk do tyłu: mniej kąta na FW albo więcej na RW / dyfuzorze. Porównaj z rozkładem masy auta — balans aero powyżej masy daje nadsterowność przy dużej prędkości.",
    })
  }

  const wheels = componentByName(kpis, /wheel/i)
  if (wheels && wheels.shareDragPct != null && wheels.shareDragPct >= 25) {
    findings.push({
      id: "wheel-drag",
      severity: "watch",
      title: "Koła zjadają za dużo drag",
      evidence: `${wheels.shareDragPct}% całego Cd jest na kołach.${fluent.wheelsRotate ? " Koła mają rotating wall w case'ie." : " W packu nie ma potwierdzenia rotacji kół."}`,
      recommendation:
        "Sprawdź, czy koła mają rotating wall albo MRF. Bez rotacji ten udział oporu nie nadaje się do porównań między geometriami.",
    })
  }

  const hoop = devices.some((device) => device.role === "roll-hoop" || device.id === "hoop")
  if (hoop && rw && rw.shareDownforcePct != null && rw.shareDragPct != null) {
    findings.push({
      id: "rw-dirty-air",
      severity: "watch",
      title: "Hoop jest w geometrii — sprawdź, czy RW stoi w jego śladzie",
      evidence: `Karta hoop jest w geometry.yaml. RW ma ${rw.shareDownforcePct}% docisku i ${rw.shareDragPct}% oporu. To nie jest odczyt z klatki.`,
      recommendation:
        "Porównaj Cp na głównym płacie RW ze stacją X za hoopem. Bez tej klatki nie nazywaj stallu.",
    })
  }

  if (kpis.LOverD != null && kpis.LOverD >= 2.4 && kpis.Cl != null && kpis.Cd != null) {
    const re = caseReynolds(fluent)
    findings.push({
      id: "lod-ok",
      severity: "info",
      title: `L/D = ${kpis.LOverD.toFixed(2)} — w normie mocnego paczka FS`,
      evidence: `Cl ${kpis.Cl}, Cd ${kpis.Cd}${re == null ? "" : `, Re ≈ ${(re / 1e6).toFixed(2)}e6`}. Downforce ${kpis.downforceN == null ? "brak" : kpis.downforceN.toFixed(0)} N / drag ${kpis.dragN == null ? "brak" : kpis.dragN.toFixed(0)} N przy ${fluent.speedMs ?? "brak"} m/s.`,
      recommendation:
        "Traktuj L/D jako KPI sezonu, ale decyzje geometryczne podejmuj na komponentach, nie na jednej liczbie z yaw 0.",
    })
  }

  const missingHero =
    images.length === 0 ||
    heroes.filter((h) => h.axis === "x").length < 6 ||
    !heroes.some((h) => h.axis === "y") ||
    !heroes.some((h) => h.axis === "z")
  if (images.length === 0) {
    findings.push({
      id: "coverage",
      severity: "blocker",
      title: "Brak indeksu klatek",
      evidence: "Pack nie ma zdjęć post-processingu.",
      recommendation: "Zindeksuj batch CFD-Post. Nie wysyłaj oceny wizualnej bez hero.",
    })
  } else if (missingHero) {
    findings.push({
      id: "coverage",
      severity: "blocker",
      title: "Brakuje hero klatek na jednej z osi",
      evidence: `Hero: ${heroes.length}. X/Y/Z muszą mieć reprezentację, inaczej opis przepływu nie ma stacji.`,
      recommendation: "Nie wysyłaj packa dopóki selector nie wybierze stacji na FW, osiach, dyfuzorze i wake.",
    })
  } else {
    findings.push({
      id: "coverage-ok",
      severity: "info",
      title: `${images.length} klatek zredukowane do ${heroes.length} hero`,
      evidence: `Pokrycie osi: full ${byAxis.full}, X ${byAxis.x}, Y ${byAxis.y}, Z ${byAxis.z}.`,
      recommendation:
        "Do pierwszego strzału dokładaj hero. Reszta zostaje w indeksie.",
    })
  }

  const questions: string[] = []
  if (fluent.yPlusWings == null) {
    questions.push("Jaki jest y+ min/avg/max na FW, RW i podłodze?")
  }
  if (!fluent.wheelsRotate) {
    questions.push("Czy koła mają rotację (MRF albo rotating wall)?")
  }
  if (fluent.yawDeg === 0) {
    questions.push("Czy jest case yaw 3° i 6° na tej samej geometrii?")
  }
  questions.push("Jakie Cl/Cd z tunelu albo z poprzedniego bolidu na tym samym setupie?")

  const nextRuns: string[] = []
  if (yPlusAvg == null || yPlusAvg > 5) {
    nextRuns.push("Mesh refinement na płatach, ten sam setup — delta Cl, Cd i y+.")
  }
  if (fluent.yawDeg === 0) {
    nextRuns.push("Yaw 0 / 3 / 6° sweep, te same hero stacje.")
  }
  if (cad.rideHeightFrontMm != null) {
    nextRuns.push(
      `Front ride height ${Math.max(10, cad.rideHeightFrontMm - 5)} vs ${cad.rideHeightFrontMm} mm — czy podłoga nie stalluje.`,
    )
  }

  const review: AgentReview = {
    verdict: "warunkowo-akceptowalne",
    summary: "",
    scores: { zbieznosc, siatka, wydajnosc, balanse, pokrycieWizualne },
    findings,
    questions,
    nextRuns,
  }

  const issues = findings.filter((f) => f.severity === "issue").length
  const blockers = findings.filter((f) => f.severity === "blocker").length
  if (blockers) review.verdict = "nieufne"
  else if (issues >= 2) review.verdict = "do-poprawy"
  else if (issues >= 1 || findings.some((f) => f.severity === "watch"))
    review.verdict = "warunkowo-akceptowalne"
  else review.verdict = "akceptowalne"

  const lodText = kpis.LOverD == null ? "L/D brak" : `L/D ${kpis.LOverD.toFixed(2)}`
  const balanceText =
    kpis.frontBalancePct == null
      ? "balans brak"
      : `balans ${kpis.frontBalancePct}% z przodu`
  const confidence =
    review.verdict === "akceptowalne"
      ? "można porównywać geometrie"
      : "nie porównuj geometrii na trzecim miejscu po przecinku, dopóki luki w packu są otwarte"
  review.summary = `Case ${fluent.name}: ${lodText}, ${balanceText}, ${heroes.length} hero z ${images.length} klatek. ${confidence}.`

  return review
}

export const VERDICT_LABEL: Record<AgentReview["verdict"], string> = {
  akceptowalne: "Akceptowalne",
  "warunkowo-akceptowalne": "Warunkowo akceptowalne",
  "do-poprawy": "Do poprawy zanim porównasz geometrie",
  nieufne: "Nieufne — pack niekompletny albo fizyka rozjechana",
}
