export type Axis = "full" | "x" | "y" | "z"

export type FieldId =
  | "cp"
  | "cpt"
  | "vel"
  | "vort"
  | "tke"
  | "helicity"
  | "yplus"
  | "u"
  | "pt"

export type RegionId =
  | "full-car"
  | "nose"
  | "front-wing"
  | "front-axle"
  | "floor-inlet"
  | "cockpit"
  | "rear-axle"
  | "diffuser"
  | "rear-wing"
  | "near-wake"
  | "far-wake"
  | "symmetry"
  | "inner-wheel"
  | "outer-wheel"
  | "ground"
  | "underfloor"
  | "sidepod"
  | "wing-height"
  | "roll-hoop"

export type Severity = "info" | "watch" | "issue" | "blocker"

export type PostImage = {
  id: string
  filename: string
  axis: Axis
  field: FieldId
  stationM: number | null
  camera: string
  zoom: "full" | "detail"
  region: RegionId
  hero: boolean
  reason?: string
}

export type ComponentForce = {
  name: string
  Cd: number
  Cl: number
  shareDownforcePct: number
  shareDragPct: number
}

export type CadModel = {
  name: string
  format: string
  triangles: number
  wheelbaseMm: number
  trackMm: number
  lengthMm: number
  widthMm: number
  heightMm: number
  frontalAreaM2: number
  rideHeightFrontMm: number
  rideHeightRearMm: number
  rakeDeg: number
  components: string[]
}

export type FluentCase = {
  id: string
  name: string
  casFile: string
  datFile: string
  solver: string
  turbulence: string
  wallTreatment: string
  cellsM: number
  speedMs: number
  yawDeg: number
  rho: number
  mu: number
  referenceAreaM2: number
  referenceLengthM: number
  iterations: number
  residuals: {
    continuity: number
    xMomentum: number
    yMomentum: number
    zMomentum: number
    k: number
    omega: number
  }
  yPlusWings: { min: number; avg: number; max: number }
  yPlusFloor: { min: number; avg: number; max: number }
}

export type AeroKpis = {
  Cd: number
  Cl: number
  Cs: number
  LOverD: number
  frontBalancePct: number
  downforceN: number
  dragN: number
  components: ComponentForce[]
}

export type ReviewFinding = {
  id: string
  severity: Severity
  title: string
  evidence: string
  recommendation: string
}

export type AgentReview = {
  verdict: "akceptowalne" | "warunkowo-akceptowalne" | "do-poprawy" | "nieufne"
  summary: string
  scores: {
    zbieznosc: number
    siatka: number
    wydajnosc: number
    balanse: number
    pokrycieWizualne: number
  }
  findings: ReviewFinding[]
  questions: string[]
  nextRuns: string[]
}

export type AgentPack = {
  schema: "aeropack/v1"
  generatedAt: string
  case: FluentCase
  cad: CadModel
  kpis: AeroKpis
  imageCatalog: {
    total: number
    byAxis: Record<Axis, number>
    byField: Partial<Record<FieldId, number>>
    heroCount: number
  }
  heroFrames: Array<{
    filename: string
    axis: Axis
    field: FieldId
    stationM: number | null
    region: RegionId
    why: string
  }>
  notesForAgent: string[]
}
