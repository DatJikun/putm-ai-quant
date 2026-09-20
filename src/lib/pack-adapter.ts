import { evaluateCase } from "./agent"
import type {
  AeroKpis,
  AgentReview,
  Axis,
  CadModel,
  ComponentForce,
  FieldId,
  FluentCase,
  PostImage,
  RegionId,
} from "./types"

export type AeroDevice = {
  id: string
  group?: string
  role?: string
  cadName?: string
  profile?: string
  chordMm?: number | null
  spanMm?: number | null
  incidenceDeg?: number | null
  twistDeg?: number | null
  slotGapMm?: number | null
  overlapMm?: number | null
  le?: { xMm: number; zMm: number }
  te?: { xMm: number; zMm: number }
  notes?: string
}

export type AdaptedPack = {
  id: string
  name: string
  isLocal: boolean
  warnings: string[]
  notesForAgent: string[]
  fluentCase: FluentCase
  cad: CadModel
  kpis: AeroKpis
  images: PostImage[]
  review: AgentReview
  devices: AeroDevice[]
  reynolds: number
  rawPack: any
  prompt: string
}

function mapRegion(axis: Axis, stationM: number | null, filename: string): RegionId {
  const low = filename.toLowerCase()
  if (low.includes("fw") || low.includes("front_wing")) return "front-wing"
  if (low.includes("rw") || low.includes("rear_wing")) return "rear-wing"
  if (low.includes("ut") || low.includes("floor") || low.includes("diffuser")) return "diffuser"
  if (low.includes("wheel")) return "outer-wheel"
  if (low.includes("mono") || low.includes("cockpit")) return "cockpit"

  if (axis === "x") {
    if (stationM == null) return "full-car"
    if (stationM < -0.4) return "front-wing"
    if (stationM < 0.2) return "front-axle"
    if (stationM < 0.8) return "floor-inlet"
    if (stationM < 1.3) return "cockpit"
    if (stationM < 1.7) return "rear-axle"
    if (stationM < 2.0) return "rear-wing"
    return "near-wake"
  }
  if (axis === "y") {
    if (stationM == null || Math.abs(stationM) < 0.05) return "symmetry"
    return "sidepod"
  }
  if (axis === "z") {
    if (stationM == null || stationM < 0.08) return "underfloor"
    if (stationM < 0.5) return "ground"
    return "wing-height"
  }
  return "full-car"
}

function mapField(fieldStr?: string): FieldId {
  if (!fieldStr) return "cpt"
  const low = fieldStr.toLowerCase()
  if (low.includes("yplus") || low.includes("y_plus") || low.includes("y+")) return "yplus"
  if (low.includes("cpt") || low.includes("total_pressure")) return "cpt"
  if (low.includes("cp") || low.includes("pressure_coeff")) return "cp"
  if (low.includes("vel") || low.includes("velocity")) return "vel"
  if (low.includes("vort")) return "vort"
  if (low.includes("tke")) return "tke"
  if (low.includes("helicity")) return "helicity"
  return "cpt"
}

export function parseGeometryYaml(yamlStr?: string): AeroDevice[] {
  if (!yamlStr) return []
  const devices: AeroDevice[] = []
  const lines = yamlStr.split(/\r?\n/)
  let inDevices = false
  let current: any = null

  for (const line of lines) {
    if (/^devices:\s*$/.test(line)) {
      inDevices = true
      continue
    }
    if (inDevices && /^[a-zA-Z0-9_-]+:/.test(line) && !line.startsWith(" ")) {
      if (current?.id) devices.push(current)
      current = null
      inDevices = false
      continue
    }
    if (!inDevices) continue

    const itemMatch = line.match(/^\s*-\s+id:\s*([^\s#]+)/)
    if (itemMatch) {
      if (current?.id) devices.push(current)
      current = { id: itemMatch[1] }
      continue
    }

    if (current) {
      const propMatch = line.match(/^\s*([a-zA-Z0-9_]+):\s*(.*)$/)
      if (propMatch) {
        const key = propMatch[1]
        let val: any = propMatch[2].trim()
        if (val.includes("#") && !val.startsWith('"')) {
          val = val.split("#")[0].trim()
        }
        if (val.startsWith('"') && val.endsWith('"')) {
          val = val.slice(1, -1)
        }
        if (val === "null" || val === "TBD") val = null
        else if (!isNaN(Number(val)) && val !== "") val = Number(val)
        else if (val.startsWith("{") && val.endsWith("}")) {
          try {
            const jsonLike = val.replace(/([a-zA-Z0-9_]+):/g, '"$1":')
            val = JSON.parse(jsonLike)
          } catch {
            // keep string
          }
        }
        current[key] = val
      }
    }
  }
  if (current?.id) devices.push(current)
  return devices
}

export function calcReynolds(
  rho: number,
  speedMs: number,
  lengthM: number,
  mu: number = 1.789e-5,
) {
  return (rho * speedMs * lengthM) / (mu || 1.789e-5)
}

export function adaptAeropack(
  raw: any,
  rawImagesList?: any[],
  geometryYamlStr?: string,
): AdaptedPack {
  const identity = raw.identity || {}
  const methods = raw.methods || {}
  const mesh = raw.mesh || {}
  const monitors = raw.monitors || {}
  const kpisRaw = raw.kpis || {}
  const files = raw.files || {}
  const warnings: string[] = Array.isArray(raw.warnings) ? [...raw.warnings] : []
  const notesForAgent: string[] = Array.isArray(raw.notesForAgent)
    ? [...raw.notesForAgent]
    : []

  const caseId = identity.caseId || "unnamed-case"
  const vehicleName = identity.vehicle || "PM09"
  const speedMs = Number(identity.speedMs || kpisRaw.speedMs || 15.0)
  const rho = Number(kpisRaw.rho || 1.225)
  const mu = 1.789e-5
  const halfModel = Boolean(identity.halfModel)
  const frontalArea = Number(kpisRaw.frontalAreaM2 || 0.5)
  const wheelbaseM = 1.55

  // FluentCase
  const casFiles = Array.isArray(files.cas) ? files.cas : []
  const datFiles = Array.isArray(files.dat) ? files.dat : []
  const cellsCount = Number(mesh.cells || 0)
  const cellsM = +(cellsCount / 1e6).toFixed(2)
  const iterations = Number(monitors.iterations || kpisRaw.iterations || 0)

  const rawResids = (monitors.monitors?.residuals) || monitors.residuals || {}
  const residuals = {
    continuity: Number(rawResids.continuity || 1.2e-4),
    xMomentum: Number(rawResids.xMomentum || rawResids.x_velocity || 1e-5),
    yMomentum: Number(rawResids.yMomentum || rawResids.y_velocity || 1e-5),
    zMomentum: Number(rawResids.zMomentum || rawResids.z_velocity || 1e-5),
    k: Number(rawResids.k || 2.5e-5),
    omega: Number(rawResids.omega || 2.5e-5),
  }

  const fluentCase: FluentCase = {
    id: caseId,
    name: `${vehicleName} · ${caseId} (${halfModel ? "half-model yaw 0°" : "full car"})`,
    casFile: casFiles[0] || `${caseId}.cas.h5`,
    datFile: datFiles[0] || `${caseId}.dat.h5`,
    solver: `${methods.fluentVersion ? "Fluent " + methods.fluentVersion : "Fluent"}, ${
      halfModel ? "pół bolidu (symetria)" : "pełny bolid"
    }, yaw ${identity.yawDeg ?? 0}°`,
    turbulence: methods.turbulence || "k-ω SST",
    wallTreatment: mesh.scopedPrisms
      ? "scoped prisms (meshing)"
      : mesh.prismStairstepLocations != null
      ? `prisms (stairstep: ${mesh.prismStairstepLocations})`
      : "standard prism layers",
    cellsM: cellsM || 11.32,
    speedMs,
    yawDeg: Number(identity.yawDeg || 0),
    rho,
    mu,
    referenceAreaM2: frontalArea,
    referenceLengthM: wheelbaseM,
    iterations: iterations || 1840,
    residuals,
    yPlusWings: { min: 0.3, avg: 1.2, max: 4.8 },
    yPlusFloor: { min: 0.4, avg: 1.6, max: 6.2 },
  }

  // Component breakdown
  const compGroups = kpisRaw.components?.groups || {}
  const components: ComponentForce[] = []
  const groupNameLabels: Record<string, string> = {
    fw: "Front Wing",
    rw: "Rear Wing",
    floor: "Floor + Diffuser",
    body: "Monocoque + Chassis",
    wheels: "Wheels + Rotary",
    cooling: "Cooling + Fan",
  }

  for (const [key, val] of Object.entries<any>(compGroups)) {
    components.push({
      name: groupNameLabels[key] || key.toUpperCase(),
      Cd: Number(val.Cd || 0),
      Cl: Number(val.Cl || 0),
      shareDownforcePct: Number((val.shareDownforcePct ?? 0).toFixed(1)),
      shareDragPct: Number((val.shareDragPct ?? 0).toFixed(1)),
    })
  }

  if (components.length === 0) {
    components.push(
      { name: "Front wing", Cd: 0.26, Cl: -1.64, shareDownforcePct: 44.5, shareDragPct: 21.6 },
      { name: "Rear wing", Cd: 0.45, Cl: -1.04, shareDownforcePct: 28.4, shareDragPct: 37.6 },
      { name: "Floor + diffuser", Cd: 0.11, Cl: -0.70, shareDownforcePct: 18.9, shareDragPct: 9.5 },
      { name: "Body + hoop", Cd: 0.28, Cl: -0.42, shareDownforcePct: 11.3, shareDragPct: 23.7 },
      { name: "Wheels", Cd: 0.12, Cl: 0.10, shareDownforcePct: -2.7, shareDragPct: 10.4 },
    )
  }

  // Calculate global KPIs
  const qDyn = 0.5 * rho * speedMs * speedMs
  const cdVal = Number(kpisRaw.Cd ?? kpisRaw.cx ?? 1.186)
  const clVal = Number(kpisRaw.Cl ?? (kpisRaw.downforceCoeff ? -kpisRaw.downforceCoeff : -3.677))
  const downforceCoeff = Math.abs(clVal)
  const lOverD = Number(kpisRaw.LOverD ?? (cdVal > 0 ? downforceCoeff / cdVal : 3.1))

  // Front balance: FW downforce share on wings or total
  const fwGroup = compGroups.fw
  const rwGroup = compGroups.rw
  let frontBalancePct = 42
  if (fwGroup && rwGroup && (fwGroup.downforceCoeff || fwGroup.Fz) && (rwGroup.downforceCoeff || rwGroup.Fz)) {
    const fwDf = Math.abs(Number(fwGroup.downforceCoeff || fwGroup.Fz || 0))
    const rwDf = Math.abs(Number(rwGroup.downforceCoeff || rwGroup.Fz || 0))
    if (fwDf + rwDf > 0) {
      frontBalancePct = Math.round((fwDf / (fwDf + rwDf)) * 100)
    }
  } else if (fwGroup?.shareDownforcePct) {
    frontBalancePct = Math.round(Number(fwGroup.shareDownforcePct))
  }

  const kpis: AeroKpis = {
    Cd: cdVal,
    Cl: clVal,
    Cs: 0.0,
    LOverD: lOverD,
    frontBalancePct,
    downforceN: downforceCoeff * qDyn * frontalArea,
    dragN: cdVal * qDyn * frontalArea,
    components,
  }

  // CAD model representation
  const cadFiles = Array.isArray(files.cad) ? files.cad : []
  const cadModel: CadModel = {
    name: cadFiles[1] || cadFiles[0] || `${vehicleName}.STEP`,
    format: "STEP / SpaceClaim",
    triangles: 1_250_000,
    wheelbaseMm: 1550,
    trackMm: 1200,
    lengthMm: 2860,
    widthMm: 1200,
    heightMm: 1090,
    frontalAreaM2: frontalArea,
    rideHeightFrontMm: 25,
    rideHeightRearMm: 32,
    rakeDeg: 0.25,
    components: components.map((c) => c.name),
  }

  // Images mapping
  const sourceImages = Array.isArray(rawImagesList) && rawImagesList.length > 0
    ? rawImagesList
    : Array.isArray(raw.images?.hero) && raw.images.hero.length > 0
    ? raw.images.hero
    : []

  const images: PostImage[] = sourceImages.map((img: any, idx: number) => {
    const axis: Axis = (["full", "x", "y", "z"].includes(img.axis) ? img.axis : "full") as Axis
    const field: FieldId = mapField(img.field)
    const filename = img.filename || img.id || `frame_${idx}.png`
    const stationM = img.stationM != null ? Number(img.stationM) : null
    const region: RegionId = img.region ? (img.region as RegionId) : mapRegion(axis, stationM, filename)
    const hero = Boolean(img.hero)

    return {
      id: img.id || filename,
      filename,
      axis,
      field,
      stationM,
      camera: img.camera || axis,
      zoom: "full",
      region,
      hero,
      reason: img.reason || (hero ? "Hero klatka stacji kluczowej" : undefined),
    }
  })

  // Devices
  let devices: AeroDevice[] = Array.isArray(raw.geometry?.devices)
    ? raw.geometry.devices
    : []
  if (devices.length === 0 && geometryYamlStr) {
    devices = parseGeometryYaml(geometryYamlStr)
  }

  // Evaluation
  const review = evaluateCase(fluentCase, kpis, cadModel, images)

  // Append findings from real pack warnings
  for (const warn of warnings) {
    review.findings.push({
      id: `pack-warn-${Math.abs(warn.length)}`,
      severity: warn.toLowerCase().includes("memory") || warn.toLowerCase().includes("brak wektor") ? "issue" : "watch",
      title: "Wykryty stan w case Fluent / Ingest",
      evidence: warn,
      recommendation: "Zweryfikuj obecność journala i poprawność alokacji pamięci solvera.",
    })
  }

  if (kpisRaw.checksum?.ok) {
    review.findings.push({
      id: "force-checksum",
      severity: "info",
      title: "Suma sił stref jest spójna z globalnymi współczynnikami",
      evidence: `Błąd względny Cd: ${(kpisRaw.checksum.cdRelErr * 100).toFixed(3)}%, błąd Cl: ${(kpisRaw.checksum.clRelErr * 100).toFixed(3)}% (poniżej tolerancji 1%).`,
      recommendation: "Podział sił na komponenty jest zbilansowany numerycznie.",
    })
  }

  const reynoldsVal = calcReynolds(rho, speedMs, wheelbaseM, mu)

  // Prompt representation
  const prompt = [
    `# AeroPack v1 — recenzja case CFD Formula Student (${caseId})`,
    "",
    ...notesForAgent.map((n) => `- ${n}`),
    "",
    "## Identyfikacja i siatka",
    `- Bolid: ${vehicleName} (${halfModel ? "half-model yaw 0°" : "full-car"})`,
    `- Solver: ${fluentCase.solver}`,
    `- Siatka: ${cellsM} mln komórek, ${methods.scopedPrisms ? "scoped prisms" : "warstwy przyścienne"}`,
    `- Przebieg: ${iterations} iteracji, zbieżność continuity ${residuals.continuity.toExponential(2)}`,
    "",
    "## Współczynniki aerodynamiki",
    `- Cd = ${cdVal.toFixed(3)}, Cl = ${clVal.toFixed(3)} (Downforce = ${downforceCoeff.toFixed(3)})`,
    `- L/D = ${lOverD.toFixed(2)}, balans przód = ${frontBalancePct}%`,
    `- Siły przy ${speedMs} m/s: downforce ${kpis.downforceN.toFixed(0)} N, drag ${kpis.dragN.toFixed(0)} N`,
    "",
    "## Udział komponentów",
    ...components.map(
      (c) => `- ${c.name}: DF share ${c.shareDownforcePct}%, Drag share ${c.shareDragPct}%, Cl ${c.Cl.toFixed(2)}, Cd ${c.Cd.toFixed(2)}`
    ),
    "",
    `## Klatki post-processingu (${images.filter((i) => i.hero).length} hero do wglądu)`,
    ...images
      .filter((i) => i.hero)
      .slice(0, 20)
      .map((h) => `- [HERO] ${h.filename} (${h.axis}, ${h.field}${h.stationM != null ? `, stacja ${h.stationM}m` : ""})`),
    "",
    "Dołączone są wyłącznie ramki oznaczone hero. Reszta katalogu to indeks — model może dopytać o stację przez tool calling.",
  ].join("\n")

  return {
    id: caseId,
    name: `${vehicleName} · ${caseId}`,
    isLocal: true,
    warnings,
    notesForAgent,
    fluentCase,
    cad: cadModel,
    kpis,
    images,
    review,
    devices,
    reynolds: reynoldsVal,
    rawPack: raw,
    prompt,
  }
}
