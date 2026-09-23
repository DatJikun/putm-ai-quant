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
  component?: string
  feature?: string
  reason?: string
}

export type ComponentForce = {
  name: string
  Cd: number | null
  Cl: number | null
  shareDownforcePct: number | null
  shareDragPct: number | null
}

export type YPlusStats = {
  min: number | null
  avg: number | null
  max: number | null
}

export type CadModel = {
  name: string
  format: string
  triangles: number | null
  wheelbaseMm: number | null
  trackMm: number | null
  lengthMm: number | null
  widthMm: number | null
  heightMm: number | null
  frontalAreaM2: number | null
  rideHeightFrontMm: number | null
  rideHeightRearMm: number | null
  rakeDeg: number | null
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
  cellsM: number | null
  speedMs: number | null
  yawDeg: number
  rho: number | null
  mu: number | null
  referenceAreaM2: number | null
  referenceLengthM: number | null
  iterations: number | null
  residuals: {
    continuity: number | null
    xMomentum: number | null
    yMomentum: number | null
    zMomentum: number | null
    k: number | null
    omega: number | null
  }
  yPlusWings: YPlusStats | null
  yPlusFloor: YPlusStats | null
  minOrthogonalQuality?: number | null
  mrfFan?: boolean
}

export type AeroKpis = {
  Cd: number | null
  Cl: number | null
  Cs: number | null
  LOverD: number | null
  frontBalancePct: number | null
  downforceN: number | null
  dragN: number | null
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
    zbieznosc: number | null
    siatka: number | null
    wydajnosc: number | null
    balanse: number | null
    pokrycieWizualne: number | null
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
