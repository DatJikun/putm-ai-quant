import { buildImageCatalog } from "./catalog"
import type { AeroKpis, CadModel, FluentCase } from "./types"

export const fluentCase: FluentCase = {
  id: "fs26-yh15-yaw0",
  name: "FS-26 · 15 m/s · yaw 0°",
  casFile: "FS26_aero_yh15_yaw0.cas.h5",
  datFile: "FS26_aero_yh15_yaw0.dat.h5",
  solver: "Fluent 2024 R2, pressure-based, steady, coupled",
  turbulence: "k-ω SST",
  wallTreatment: "low-Re, y+ ≈ 1 na skrzydłach (założenie setupu)",
  cellsM: 18.4,
  speedMs: 15,
  yawDeg: 0,
  rho: 1.225,
  mu: 1.789e-5,
  referenceAreaM2: 0.92,
  referenceLengthM: 1.6,
  iterations: 4200,
  residuals: {
    continuity: 1.2e-4,
    xMomentum: 8.4e-6,
    yMomentum: 6.1e-6,
    zMomentum: 7.3e-6,
    k: 3.2e-5,
    omega: 2.8e-5,
  },
  yPlusWings: { min: 0.4, avg: 42, max: 118 },
  yPlusFloor: { min: 0.6, avg: 11, max: 54 },
}

export const cad: CadModel = {
  name: "FS-26_aero_assembly_v14.step",
  format: "STEP + STL powierzchni ścian",
  triangles: 1_842_000,
  wheelbaseMm: 1600,
  trackMm: 1200,
  lengthMm: 2980,
  widthMm: 1190,
  heightMm: 980,
  frontalAreaM2: 0.92,
  rideHeightFrontMm: 25,
  rideHeightRearMm: 32,
  rakeDeg: 0.25,
  components: [
    "front wing (main + 3 flaps + endplates)",
    "nose / chassis",
    "front wheels + uprights",
    "floor + diffuser",
    "sidepods + radiator ducts",
    "cockpit + driver + roll hoop",
    "rear wheels",
    "rear wing (main + 2 flaps + DRS closed)",
  ],
}

const demoRho = fluentCase.rho as number
const demoSpeed = fluentCase.speedMs as number
const demoArea = fluentCase.referenceAreaM2 as number
const demoLength = fluentCase.referenceLengthM as number
const demoMu = fluentCase.mu as number

const qDyn = 0.5 * demoRho * demoSpeed * demoSpeed

export const kpis: AeroKpis = {
  Cd: 1.42,
  Cl: -3.65,
  Cs: 0.01,
  LOverD: 3.65 / 1.42,
  frontBalancePct: 41,
  downforceN: 3.65 * qDyn * demoArea,
  dragN: 1.42 * qDyn * demoArea,
  components: [
    { name: "Front wing", Cd: 0.28, Cl: -1.12, shareDownforcePct: 31, shareDragPct: 20 },
    { name: "Floor + diffuser", Cd: 0.19, Cl: -1.45, shareDownforcePct: 40, shareDragPct: 13 },
    { name: "Rear wing", Cd: 0.31, Cl: -0.88, shareDownforcePct: 24, shareDragPct: 22 },
    { name: "Wheels + wishbones", Cd: 0.38, Cl: -0.08, shareDownforcePct: 2, shareDragPct: 27 },
    { name: "Body + hoop + driver", Cd: 0.26, Cl: -0.12, shareDownforcePct: 3, shareDragPct: 18 },
  ],
}

export function reynolds() {
  return (demoRho * demoSpeed * demoLength) / demoMu
}

export function getDemoImages() {
  return buildImageCatalog()
}
