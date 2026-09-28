import assert from "node:assert/strict"
import { test } from "node:test"
import { VERDICT_LABEL, evaluateCase, type ReviewDevice } from "../src/lib/agent"
import { adaptAeropack } from "../src/lib/pack-adapter"
import * as demo from "../src/lib/demo-case"
import type { AeroKpis, AgentReview, Axis, CadModel, FluentCase, PostImage } from "../src/lib/types"

// A case that has nothing to complain about. Each test changes one thing.
function goodCase(over: Partial<FluentCase> = {}): FluentCase {
  return {
    id: "c1",
    name: "PM09 · test",
    casFile: "a.cas.h5",
    datFile: "a.dat.h5",
    solver: "Fluent 2023 R1",
    turbulence: "k-omega SST",
    wallTreatment: "scoped prisms (meshing)",
    cellsM: 18,
    speedMs: 15,
    yawDeg: 5,
    rho: 1.225,
    mu: 1.789e-5,
    referenceAreaM2: 0.5,
    referenceLengthM: 1.53,
    iterations: 2000,
    residuals: { continuity: 1e-6, xMomentum: 1e-6, yMomentum: 1e-6, zMomentum: 1e-6, k: 1e-6, omega: 1e-6 },
    yPlusWings: { min: 0.5, avg: 1.2, max: 3 },
    yPlusFloor: { min: 0.5, avg: 2, max: 5 },
    minOrthogonalQuality: 0.2,
    wheelsRotate: true,
    solverCrashes: [],
    solverSessionCount: 1,
    forcesSettled: true,
    forceDriftReasons: [],
    iterationsLeft: 0,
    plannedIterations: 2000,
    ...over,
  }
}

function goodKpis(over: Partial<AeroKpis> = {}): AeroKpis {
  return {
    Cd: 1.2,
    Cl: -3.6,
    Cs: 0,
    LOverD: 3,
    frontBalancePct: 46,
    balanceAxles: { front: 1.66, rear: 1.94 },
    downforceN: 400,
    dragN: 133,
    components: [
      { name: "Front Wing", Cd: 0.2, Cl: -1, shareDownforcePct: 30, shareDragPct: 15 },
      { name: "Rear Wing", Cd: 0.3, Cl: -1, shareDownforcePct: 30, shareDragPct: 20 },
      { name: "Wheels + Rotary", Cd: 0.3, Cl: 0, shareDownforcePct: 0, shareDragPct: 20 },
    ],
    ...over,
  }
}

function goodCad(over: Partial<CadModel> = {}): CadModel {
  return {
    name: "m.STEP",
    format: "STEP",
    triangles: null,
    wheelbaseMm: 1530,
    trackMm: null,
    lengthMm: null,
    widthMm: null,
    heightMm: null,
    frontalAreaM2: 0.5,
    rideHeightFrontMm: 30,
    rideHeightRearMm: 35,
    rakeDeg: 0.2,
    components: [],
    ...over,
  }
}

function frames(counts: { x?: number; y?: number; z?: number; full?: number }, heroes: Partial<Record<Axis, number>> = {}) {
  const out: PostImage[] = []
  for (const axis of ["full", "x", "y", "z"] as Axis[]) {
    const total = counts[axis] ?? 0
    const heroCount = heroes[axis] ?? 0
    for (let i = 0; i < total; i++) {
      out.push({
        id: `${axis}-${i}`,
        filename: `${axis}_${i}.png`,
        axis,
        field: "cpt",
        stationM: i / 10,
        camera: axis,
        zoom: "full",
        region: "full-car",
        hero: i < heroCount,
      })
    }
  }
  return out
}

// 12 heroes on all three axes: nothing to complain about in coverage.
const GOOD_IMAGES = () => frames({ x: 10, y: 3, z: 3, full: 2 }, { x: 8, y: 2, z: 2 })

function review(
  parts: { fluent?: Partial<FluentCase>; kpis?: Partial<AeroKpis>; cad?: Partial<CadModel>; images?: PostImage[]; devices?: ReviewDevice[] } = {},
): AgentReview {
  return evaluateCase(
    goodCase(parts.fluent),
    goodKpis(parts.kpis),
    goodCad(parts.cad),
    parts.images ?? GOOD_IMAGES(),
    parts.devices ?? [],
  )
}

const ids = (r: AgentReview) => r.findings.map((f) => f.id)
const finding = (r: AgentReview, id: string) => r.findings.find((f) => f.id === id)

test("a clean case is acceptable and only carries info findings", () => {
  const r = review()
  assert.equal(r.verdict, "akceptowalne")
  assert.deepEqual(ids(r), ["lod-ok", "coverage-ok"])
  assert.ok(r.findings.every((f) => f.severity === "info"))
  assert.deepEqual(r.scores, { zbieznosc: 86, siatka: 88, wydajnosc: 92, balanse: 92, pokrycieWizualne: 73 })
})

test("verdict ladder: blocker beats issues, two issues, one issue, watch, info", () => {
  assert.equal(review({ kpis: { Cd: null } }).verdict, "nieufne")
  const blockerAndIssues = review({
    kpis: { Cd: null },
    fluent: { residuals: { ...goodCase().residuals, continuity: 1e-2 }, forcesSettled: false },
  })
  assert.equal(blockerAndIssues.verdict, "nieufne")

  const twoIssues = review({ fluent: { residuals: { ...goodCase().residuals, continuity: 1e-3 }, forcesSettled: false } })
  assert.equal(twoIssues.verdict, "do-poprawy")

  const oneIssue = review({ fluent: { residuals: { ...goodCase().residuals, continuity: 1e-3 } } })
  assert.equal(oneIssue.verdict, "warunkowo-akceptowalne")

  const watchOnly = review({ fluent: { iterationsLeft: 100 } })
  assert.equal(watchOnly.verdict, "warunkowo-akceptowalne")
  assert.equal(finding(watchOnly, "stopped-early")?.severity, "watch")

  assert.equal(review().verdict, "akceptowalne")
})

test("missing Cd or Cl is a blocker and holds back the L/D note", () => {
  for (const kpis of [{ Cd: null }, { Cl: null }]) {
    const r = review({ kpis })
    assert.equal(finding(r, "kpi-missing")?.severity, "blocker")
    assert.equal(finding(r, "lod-ok"), undefined)
    assert.equal(r.verdict, "nieufne")
  }
})

test("continuity: strict 1e-4 threshold, score falls with the exponent, never below 0", () => {
  const withContinuity = (value: number | null) =>
    review({ fluent: { residuals: { ...goodCase().residuals, continuity: value } } })

  const missing = withContinuity(null)
  assert.equal(missing.scores.zbieznosc, null)
  assert.equal(finding(missing, "resid-missing")?.severity, "issue")

  const justUnder = withContinuity(9.9e-5)
  assert.equal(finding(justUnder, "resid-cont"), undefined)
  assert.equal(justUnder.scores.zbieznosc, 86)

  const atThreshold = withContinuity(1e-4)
  assert.equal(finding(atThreshold, "resid-cont")?.severity, "issue")
  assert.equal(atThreshold.scores.zbieznosc, 80)
  assert.equal(withContinuity(1e-3).scores.zbieznosc, 76)
  assert.equal(withContinuity(1).scores.zbieznosc, 64)
  assert.equal(withContinuity(1e20).scores.zbieznosc, 0)
  assert.match(finding(atThreshold, "resid-cont")!.evidence, /2000 iteracjach/)
  assert.match(finding(atThreshold, "resid-cont")!.evidence, /1\.00e-4/)
})

test("force drift and early stop are reported from the pack's own convergence data", () => {
  const drifting = review({ fluent: { forcesSettled: false, forceDriftReasons: ["cz dryfuje 0,8%", "balans 1,2 pp"] } })
  assert.equal(finding(drifting, "forces-drift")?.severity, "issue")
  assert.equal(finding(drifting, "forces-drift")?.evidence, "cz dryfuje 0,8%; balans 1,2 pp")
  for (const settled of [true, null]) {
    assert.equal(finding(review({ fluent: { forcesSettled: settled } }), "forces-drift"), undefined)
  }

  const early = review({ fluent: { iterationsLeft: 300, plannedIterations: 2000 } })
  assert.match(finding(early, "stopped-early")!.evidence, /Zabrakło 300 z 2000/)
  assert.match(finding(review({ fluent: { iterationsLeft: 300, plannedIterations: null } }), "stopped-early")!.evidence, /z \?/)
  for (const left of [0, null]) {
    assert.equal(finding(review({ fluent: { iterationsLeft: left } }), "stopped-early"), undefined)
  }
})

test("y+ missing everywhere is a watch item, on the floor alone it is not", () => {
  const none = review({ fluent: { yPlusWings: null, yPlusFloor: null } })
  assert.equal(finding(none, "yplus-missing")?.severity, "watch")
  assert.ok(none.questions.some((q) => q.startsWith("Jaki jest y+")))
  assert.ok(none.nextRuns.some((run) => run.startsWith("Mesh refinement")))

  const floorOnly = review({ fluent: { yPlusWings: null } })
  assert.equal(finding(floorOnly, "yplus-missing"), undefined)
  assert.ok(floorOnly.questions.some((q) => q.startsWith("Jaki jest y+")), "wings y+ is still unknown")
})

test("y+ against a resolved-wall setup: over 5 on the wings is an issue and costs mesh score", () => {
  const off = review({ fluent: { wallResolved: true, yPlusWings: { min: 0.4, avg: 40, max: 120 } } })
  const issue = finding(off, "yplus-wings")
  assert.equal(issue?.severity, "issue")
  assert.match(issue!.evidence, /y\+ średnie = 40/)
  assert.match(issue!.evidence, /max 120/)
  assert.equal(off.scores.siatka, 60)

  const atFive = review({ fluent: { wallResolved: true, yPlusWings: { min: 1, avg: 5, max: 9 } } })
  assert.equal(finding(atFive, "yplus-wings"), undefined)
  assert.equal(atFive.scores.siatka, 88)
  assert.ok(!atFive.nextRuns.some((run) => run.startsWith("Mesh refinement")))

  const justOver = review({ fluent: { wallResolved: true, yPlusWings: { min: 1, avg: 5.1, max: 9 } } })
  assert.equal(finding(justOver, "yplus-wings")?.severity, "issue")
  assert.equal(justOver.scores.siatka, 60)
  assert.ok(justOver.nextRuns.some((run) => run.startsWith("Mesh refinement")))

  // Wall functions, or a setup that does not say: y+ ~ 40 is expected, nothing to flag.
  for (const wallResolved of [false, null, undefined]) {
    const r = review({ fluent: { wallResolved, yPlusWings: { min: 1, avg: 40, max: 120 } } })
    assert.equal(finding(r, "yplus-wings"), undefined, String(wallResolved))
  }
})

test("mesh score: cell count under 12M, low orthogonal quality, and no data at all", () => {
  assert.equal(review({ fluent: { cellsM: 11.3 } }).scores.siatka, 73)
  assert.equal(review({ fluent: { cellsM: 12 } }).scores.siatka, 88)

  const low = review({ fluent: { minOrthogonalQuality: 0.04 } })
  assert.equal(low.scores.siatka, 68)
  assert.equal(finding(low, "ortho-low"), undefined, "0.04 costs score but is not yet an alarm")
  assert.equal(review({ fluent: { minOrthogonalQuality: 0.05 } }).scores.siatka, 88)

  const bad = review({ fluent: { minOrthogonalQuality: 0.009 } })
  assert.equal(bad.scores.siatka, 53)
  assert.equal(finding(bad, "ortho-low")?.severity, "issue")
  assert.match(finding(bad, "ortho-low")!.evidence, /0\.009/)

  const empty = review({ fluent: { cellsM: null, yPlusWings: null, minOrthogonalQuality: null } })
  assert.equal(empty.scores.siatka, null)
})

test("solver crashes: every session crashed is an issue, some is a watch", () => {
  const all = review({ fluent: { solverCrashes: ["a.trn: BAD TERMINATION"], solverSessionCount: 1 } })
  assert.equal(finding(all, "solver-crash")?.severity, "issue")
  assert.match(finding(all, "solver-crash")!.title, /Każdy transcript/)

  const some = review({ fluent: { solverCrashes: ["a.trn: x"], solverSessionCount: 3 } })
  assert.equal(finding(some, "solver-crash")?.severity, "watch")
  assert.match(finding(some, "solver-crash")!.title, /1 z 3 sesji/)

  const unknownCount = review({ fluent: { solverCrashes: ["a.trn: x"], solverSessionCount: undefined } })
  assert.equal(finding(unknownCount, "solver-crash")?.severity, "issue")
  assert.equal(finding(review(), "solver-crash"), undefined)
})

test("front balance: the 44–48% band is quiet, outside it names the side", () => {
  for (const pct of [44, 46, 48]) {
    const r = review({ kpis: { frontBalancePct: pct } })
    assert.equal(finding(r, "balance-rear"), undefined, String(pct))
    assert.equal(finding(r, "balance-front"), undefined, String(pct))
  }
  assert.equal(finding(review({ kpis: { frontBalancePct: 43.9 } }), "balance-rear")?.severity, "watch")
  assert.equal(finding(review({ kpis: { frontBalancePct: 48.1 } }), "balance-front")?.severity, "watch")
  const missing = review({ kpis: { frontBalancePct: null, balanceAxles: null } })
  assert.equal(finding(missing, "balance-rear"), undefined)
  assert.equal(finding(missing, "balance-front"), undefined)
  assert.equal(missing.scores.balanse, null)

  const withAxles = finding(review({ kpis: { frontBalancePct: 40 } }), "balance-rear")!
  assert.match(withAxles.evidence, /przedniej 1\.660, na tylnej 1\.940/)
  assert.match(withAxles.evidence, /Ride height 30\/35 mm, rake 0\.2°/)
  const noAxles = finding(review({ kpis: { frontBalancePct: 40, balanceAxles: null }, cad: { rideHeightFrontMm: null } }), "balance-rear")!
  assert.match(noAxles.evidence, /Balans z monitora cm/)
  assert.doesNotMatch(noAxles.evidence, /Ride height/)
})

test("scores for L/D and balance: sweet spot 92, inside the range 72, outside 38", () => {
  const lod = (v: number | null) => review({ kpis: { LOverD: v } }).scores.wydajnosc
  assert.deepEqual([2.4, 3, 3.2].map(lod), [92, 92, 92])
  assert.deepEqual([1.8, 2.39, 3.21, 3.6].map(lod), [72, 72, 72, 72])
  assert.deepEqual([1.79, 3.61].map(lod), [38, 38])
  assert.equal(lod(null), null)

  const bal = (v: number | null) => review({ kpis: { frontBalancePct: v } }).scores.balanse
  assert.deepEqual([44, 48].map(bal), [92, 92])
  assert.deepEqual([38, 43.9, 48.1, 52].map(bal), [72, 72, 72, 72])
  assert.deepEqual([37.9, 52.1].map(bal), [38, 38])
})

test("wheel drag: 25% of Cd or more is flagged and the text follows the rotation flag", () => {
  const withWheels = (share: number | null, wheelsRotate: boolean | null) =>
    review({
      fluent: { wheelsRotate },
      kpis: { components: [{ name: "Wheels + Rotary", Cd: 0.3, Cl: 0, shareDownforcePct: 0, shareDragPct: share }] },
    })
  assert.equal(finding(withWheels(24.9, true), "wheel-drag"), undefined)
  assert.equal(finding(withWheels(null, true), "wheel-drag"), undefined)
  assert.equal(finding(withWheels(25, true), "wheel-drag")?.severity, "watch")
  assert.match(finding(withWheels(30, true), "wheel-drag")!.evidence, /rotating wall w case'ie/)
  assert.match(finding(withWheels(30, false), "wheel-drag")!.evidence, /nie ma potwierdzenia rotacji/)
  assert.match(finding(withWheels(30, null), "wheel-drag")!.evidence, /nie ma potwierdzenia rotacji/)
})

test("hoop note appears only with a hoop card and Rear Wing shares", () => {
  const hoopByRole: ReviewDevice[] = [{ id: "x", role: "roll-hoop" }]
  const hoopById: ReviewDevice[] = [{ id: "hoop" }]
  assert.equal(finding(review({ devices: hoopByRole }), "rw-dirty-air")?.severity, "watch")
  assert.equal(finding(review({ devices: hoopById }), "rw-dirty-air")?.severity, "watch")
  assert.match(finding(review({ devices: hoopById }), "rw-dirty-air")!.evidence, /30% docisku i 20% oporu/)

  assert.equal(finding(review({ devices: [{ id: "fw-main" }] }), "rw-dirty-air"), undefined)
  assert.equal(finding(review(), "rw-dirty-air"), undefined)
  const noRw = review({ devices: hoopById, kpis: { components: [] } })
  assert.equal(finding(noRw, "rw-dirty-air"), undefined)
  const noShares = review({
    devices: hoopById,
    kpis: { components: [{ name: "Rear Wing", Cd: 0.3, Cl: -1, shareDownforcePct: null, shareDragPct: null }] },
  })
  assert.equal(finding(noShares, "rw-dirty-air"), undefined)
})

test("L/D note needs 2.4 and both coefficients, and only quotes Re when it can compute it", () => {
  assert.equal(finding(review({ kpis: { LOverD: 2.39 } }), "lod-ok"), undefined)
  const ok = finding(review({ kpis: { LOverD: 2.4 } }), "lod-ok")!
  assert.equal(ok.severity, "info")
  assert.match(ok.title, /L\/D = 2\.40/)
  // Re = 1.225 * 15 * 1.53 / 1.789e-5 = 1.57e6
  assert.match(ok.evidence, /Re ≈ 1\.57e6/)
  assert.match(ok.evidence, /Downforce 400 N \/ drag 133 N przy 15 m\/s/)

  const noMu = finding(review({ fluent: { mu: null }, kpis: { downforceN: null, dragN: null } }), "lod-ok")!
  assert.doesNotMatch(noMu.evidence, /Re ≈/)
  assert.match(noMu.evidence, /Downforce brak N \/ drag brak N/)
})

test("frame coverage: none, missing an axis, too few X heroes, and enough", () => {
  const none = review({ images: [] })
  assert.equal(finding(none, "coverage")?.severity, "blocker")
  assert.match(finding(none, "coverage")!.title, /Brak indeksu klatek/)
  assert.equal(none.scores.pokrycieWizualne, null)
  assert.equal(none.verdict, "nieufne")

  const fewX = review({ images: frames({ x: 10, y: 3, z: 3 }, { x: 5, y: 2, z: 2 }) })
  assert.match(finding(fewX, "coverage")!.title, /Brakuje hero/)
  assert.equal(fewX.verdict, "nieufne")
  const noY = review({ images: frames({ x: 10, y: 3, z: 3 }, { x: 8, z: 2 }) })
  assert.equal(finding(noY, "coverage")?.severity, "blocker")
  const noZ = review({ images: frames({ x: 10, y: 3, z: 3 }, { x: 8, y: 2 }) })
  assert.equal(finding(noZ, "coverage")?.severity, "blocker")

  const enough = review({ images: frames({ x: 10, y: 3, z: 3 }, { x: 6, y: 1, z: 1 }) })
  assert.equal(finding(enough, "coverage"), undefined)
  assert.match(finding(enough, "coverage-ok")!.title, /16 klatek zredukowane do 8 hero/)
})

test("visual coverage score: thresholds are strictly above 400 / 200 / 300 frames and 12 heroes", () => {
  const score = (counts: Parameters<typeof frames>[0], heroes: Partial<Record<Axis, number>>) =>
    review({ images: frames(counts, heroes) }).scores.pokrycieWizualne
  assert.equal(score({ x: 401, y: 201, z: 301 }, { x: 8, y: 2, z: 2 }), 94)
  assert.equal(score({ x: 400, y: 200, z: 300 }, { x: 8, y: 2, z: 2 }), 73)
  assert.equal(score({ x: 8 }, { x: 8 }), 40 + 8 + 6)
  assert.equal(score({ full: 3 }, {}), 40)
})

test("questions and next runs follow yaw, wheel rotation, y+ and ride height", () => {
  const base = review()
  assert.ok(!base.questions.some((q) => q.includes("yaw 3°")), "yaw 5 needs no sweep question")
  assert.ok(!base.questions.some((q) => q.includes("rotację")))
  assert.ok(base.questions.at(-1)!.startsWith("Jakie Cl/Cd z tunelu"))
  assert.ok(!base.nextRuns.some((run) => run.startsWith("Yaw 0")))
  assert.ok(!base.nextRuns.some((run) => run.startsWith("Mesh refinement")), "y+ 1.2 is fine")
  assert.deepEqual(base.nextRuns, ["Front ride height 25 vs 30 mm — czy podłoga nie stalluje."])

  const yaw0 = review({ fluent: { yawDeg: 0 } })
  assert.ok(yaw0.questions.some((q) => q.includes("yaw 3° i 6°")))
  assert.ok(yaw0.nextRuns.some((run) => run.startsWith("Yaw 0 / 3 / 6°")))

  for (const wheelsRotate of [false, null] as const) {
    assert.ok(review({ fluent: { wheelsRotate } }).questions.some((q) => q.includes("rotację")))
  }

  assert.ok(review({ fluent: { yPlusWings: { min: 1, avg: 6, max: 9 } } }).nextRuns.some((run) => run.startsWith("Mesh refinement")))
  assert.deepEqual(review({ cad: { rideHeightFrontMm: null } }).nextRuns, [])
  // Ride height is never suggested below 10 mm.
  assert.match(review({ cad: { rideHeightFrontMm: 12 } }).nextRuns[0], /Front ride height 10 vs 12 mm/)
})

test("summary quotes the numbers, or says they are missing", () => {
  const good = review()
  assert.equal(
    good.summary,
    "Case PM09 · test: L/D 3.00, balans 46% z przodu, 12 hero z 18 klatek. można porównywać geometrie.",
  )
  assert.match(review({ kpis: { LOverD: null, frontBalancePct: null } }).summary, /L\/D brak, balans brak/)
  const notGood = review({ fluent: { iterationsLeft: 5 } })
  assert.match(notGood.summary, /nie porównuj geometrii na trzecim miejscu po przecinku/)
})

test("every verdict has a label", () => {
  assert.deepEqual(Object.keys(VERDICT_LABEL).sort(), ["akceptowalne", "do-poprawy", "nieufne", "warunkowo-akceptowalne"])
  for (const label of Object.values(VERDICT_LABEL)) assert.ok(label.length > 0)
})

test("the synthetic demo case keeps its story: two issues, so it is not comparable yet", () => {
  const images = demo.getDemoImages()
  const r = evaluateCase(demo.fluentCase, demo.kpis, demo.cad, images)
  assert.equal(r.verdict, "do-poprawy")
  assert.deepEqual(
    r.findings.filter((f) => f.severity === "issue").map((f) => f.id).sort(),
    ["resid-cont", "yplus-wings"],
  )
})

// The adapter must hand the setup's wall treatment over, or the y+ rule never fires on real packs.
function adaptedWith(wallTreatment: string | null | undefined, yWings: number) {
  return adaptAeropack({
    schema: "aeropack/v1",
    identity: { caseId: "c", vehicle: "X", halfModel: true, yawDeg: 0 },
    methods: { turbulence: "k-omega SST", ...(wallTreatment === undefined ? {} : { wallTreatment }) },
    mesh: { cells: 18e6 },
    monitors: {
      iterations: 2000,
      residuals: { continuity: 1e-6 },
      yPlus: { wings: { min: 1, avg: yWings, max: yWings * 3 } },
    },
    kpis: { Cd: 1.2, Cl: -3.6 },
    warnings: [],
    notesForAgent: [],
  })
}

test("adapter: a setup without wall functions plus wing y+ of 40 is flagged", () => {
  for (const wall of ["k-omega (bez funkcji ściany)", "resolved (y+ ~ 1)"]) {
    const adapted = adaptedWith(wall, 40)
    assert.equal(adapted.fluentCase.wallResolved, true, wall)
    assert.equal(finding(adapted.review, "yplus-wings")?.severity, "issue", wall)
  }
  assert.equal(finding(adaptedWith("k-omega (bez funkcji ściany)", 1.5).review, "yplus-wings"), undefined)
})

test("adapter: wall functions or an unknown wall treatment do not raise the y+ issue", () => {
  for (const wall of ["Standard Wall Functions", "Scalable Wall Functions", "Enhanced Wall Treatment"]) {
    const adapted = adaptedWith(wall, 40)
    assert.equal(adapted.fluentCase.wallResolved, false, wall)
    assert.equal(finding(adapted.review, "yplus-wings"), undefined, wall)
  }
  for (const wall of [null, undefined]) {
    const adapted = adaptedWith(wall, 40)
    assert.equal(adapted.fluentCase.wallResolved, null)
    assert.equal(finding(adapted.review, "yplus-wings"), undefined)
  }
})
