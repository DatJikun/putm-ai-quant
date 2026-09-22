import assert from "node:assert/strict"
import { test } from "node:test"
import { adaptAeropack } from "../src/lib/pack-adapter"

test("adapter leaves missing solver fields empty", () => {
  const adapted = adaptAeropack(
    {
      schema: "aeropack/v1",
      identity: { caseId: "empty", vehicle: "X", halfModel: true, yawDeg: 0 },
      methods: {},
      mesh: {},
      monitors: {},
      kpis: {},
      warnings: [],
      notesForAgent: [],
      images: { total: 0, hero: [] },
    },
    [],
    "vehicle:\n  name: X\n  rideHeightFrontMm: TBD\n",
  )

  assert.equal(adapted.kpis.Cd, null)
  assert.equal(adapted.kpis.Cl, null)
  assert.equal(adapted.kpis.frontBalancePct, null)
  assert.equal(adapted.kpis.components.length, 0)
  assert.equal(adapted.fluentCase.residuals.continuity, null)
  assert.equal(adapted.fluentCase.yPlusWings, null)
  assert.equal(adapted.fluentCase.iterations, null)
  assert.equal(adapted.fluentCase.cellsM, null)
  assert.equal(adapted.fluentCase.turbulence, "nieodczytany")
  assert.equal(adapted.cad.triangles, null)
  assert.equal(adapted.cad.rideHeightFrontMm, null)
  assert.equal(adapted.cad.wheelbaseMm, null)
  assert.ok(adapted.dataGaps.includes("Brak Cd."))
  assert.ok(adapted.dataGaps.includes("Brak residualu continuity."))
  assert.equal(
    adapted.review.findings.some((finding) => finding.id === "rw-dirty-air"),
    false,
  )
  assert.equal(adapted.review.scores.zbieznosc, null)
  assert.equal(adapted.review.verdict, "nieufne")
  assert.equal(adapted.prompt.includes("1.186"), false)
  assert.equal(adapted.prompt.includes("3.677"), false)
})

test("adapter reads residuals, y+ and zone checksum from the pack", () => {
  const adapted = adaptAeropack(
    {
      schema: "aeropack/v1",
      identity: { caseId: "pm", vehicle: "PM09", halfModel: true, yawDeg: 0, speedMs: 15 },
      methods: { turbulence: "k-omega", mrfFan: false },
      mesh: { cells: 11_300_000, minOrthogonalQuality: 0.15 },
      monitors: {
        iterations: 1840,
        residuals: { continuity: 4.2e-5, xMomentum: 1e-5 },
        yPlus: { wings: { avg: 1.8, max: 4.4 }, floor: { avg: 2.4 } },
      },
      kpis: {
        Cd: 1.2,
        Cl: -3.1,
        rho: 1.225,
        frontalAreaM2: 0.5,
        components: {
          checksum: { ok: true, cdRelErr: 0.001, clRelErr: 0.002 },
          groups: {
            fw: { Cd: 0.3, Cl: -1.4, downforceCoeff: 1.4, shareDownforcePct: 45, shareDragPct: 25 },
            rw: { Cd: 0.4, Cl: -1.0, downforceCoeff: 1.0, shareDownforcePct: 32, shareDragPct: 33 },
          },
        },
      },
      warnings: [],
      notesForAgent: [],
    },
    [],
    "vehicle:\n  name: PM09\n  wheelbaseMm: 1550\n  rideHeightFrontMm: 25\n  rideHeightRearMm: 30\ndevices:\n  - id: hoop\n    role: roll-hoop\n",
  )

  assert.equal(adapted.fluentCase.residuals.continuity, 4.2e-5)
  assert.equal(adapted.fluentCase.yPlusWings?.avg, 1.8)
  assert.equal(adapted.fluentCase.cellsM, 11.3)
  assert.equal(adapted.fluentCase.iterations, 1840)
  assert.equal(adapted.kpis.Cd, 1.2)
  assert.equal(adapted.kpis.Cl, -3.1)
  assert.equal(adapted.kpis.components.length, 2)
  assert.equal(adapted.kpis.frontBalancePct, 58)
  assert.equal(adapted.cad.wheelbaseMm, 1550)
  assert.equal(adapted.cad.triangles, null)
  assert.ok(adapted.review.findings.some((finding) => finding.id === "force-checksum"))
  assert.ok(adapted.review.findings.some((finding) => finding.id === "rw-dirty-air"))
})
