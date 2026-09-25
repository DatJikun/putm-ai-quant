import { evaluateCase, type ReviewDevice } from "./agent"
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
  reynolds: number | null
  dataGaps: string[]
  rawPack: any
  prompt: string
}

function num(value: unknown): number | null {
  if (typeof value === "boolean" || value == null || value === "") return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function fmt(value: number | null, digits = 2, suffix = "") {
  if (value == null) return "brak"
  return `${value.toFixed(digits)}${suffix}`
}

function readYPlus(block: unknown) {
  if (!block || typeof block !== "object") return null
  const source = block as Record<string, unknown>
  const min = num(source.min)
  const avg = num(source.avg)
  const max = num(source.max)
  if (min == null && avg == null && max == null) return null
  return { min, avg, max }
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

export function parseVehicleYaml(yamlStr?: string): Record<string, string | number | null> {
  if (!yamlStr) return {}
  const lines = yamlStr.split(/\r?\n/)
  let inVehicle = false
  const vehicle: Record<string, string | number | null> = {}
  for (const line of lines) {
    if (/^vehicle:\s*$/.test(line)) {
      inVehicle = true
      continue
    }
    if (inVehicle && /^[a-zA-Z]/.test(line)) break
    if (!inVehicle) continue
    const propMatch = line.match(/^\s+([a-zA-Z0-9_]+):\s*(.*)$/)
    if (!propMatch) continue
    let val = propMatch[2].trim()
    if (val.includes("#") && !val.startsWith('"')) val = val.split("#")[0].trim()
    if (val.startsWith('"') && val.endsWith('"')) val = val.slice(1, -1)
    if (val === "null" || val === "TBD" || val === "") vehicle[propMatch[1]] = null
    else if (!Number.isNaN(Number(val))) vehicle[propMatch[1]] = Number(val)
    else vehicle[propMatch[1]] = val
  }
  return vehicle
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
  const vehicleYaml = parseVehicleYaml(geometryYamlStr)
  const vehicleName =
    (typeof identity.vehicle === "string" && identity.vehicle) ||
    (typeof vehicleYaml.name === "string" && vehicleYaml.name) ||
    "nieznany bolid"
  const speedMs = num(identity.speedMs) ?? num(kpisRaw.speedMs)
  const rho = num(kpisRaw.rho)
  const mu = num(kpisRaw.references?.mu?.value) ?? num(kpisRaw.mu)
  const halfModel = Boolean(identity.halfModel)
  const frontalArea = num(kpisRaw.frontalAreaM2) ?? num(vehicleYaml.frontalAreaM2)
  const wheelbaseMm = num(vehicleYaml.wheelbaseMm)
  const wheelbaseM = wheelbaseMm == null ? null : wheelbaseMm / 1000
  const dataGaps: string[] = []

  const casFiles = Array.isArray(files.cas) ? files.cas : []
  const datFiles = Array.isArray(files.dat) ? files.dat : []
  const cellsCount = num(mesh.cells)
  const cellsM = cellsCount == null ? null : +(cellsCount / 1e6).toFixed(2)
  const iterations = num(monitors.iterations) ?? num(kpisRaw.iterations)

  const rawResids = monitors.residuals || monitors.monitors?.residuals || {}
  const residuals = {
    continuity: num(rawResids.continuity),
    xMomentum: num(rawResids.xMomentum) ?? num(rawResids.x_velocity),
    yMomentum: num(rawResids.yMomentum) ?? num(rawResids.y_velocity),
    zMomentum: num(rawResids.zMomentum) ?? num(rawResids.z_velocity),
    k: num(rawResids.k),
    omega: num(rawResids.omega),
  }
  const yPlusBlock = monitors.yPlus || {}
  const yPlusWings = readYPlus(yPlusBlock.wings)
  const yPlusFloor = readYPlus(yPlusBlock.floor)

  if (cellsM == null) dataGaps.push("Liczba komórek nie została odczytana z transcriptu.")
  if (iterations == null) dataGaps.push("Liczba iteracji nie została odczytana z monitorów.")
  if (residuals.continuity == null) dataGaps.push("Brak residualu continuity.")
  if (yPlusWings == null && yPlusFloor == null) dataGaps.push("Brak statystyk y+.")
  if (speedMs == null) dataGaps.push("Brak V∞.")
  if (frontalArea == null) dataGaps.push("Brak Aref.")

  const fluentCase: FluentCase = {
    id: caseId,
    name: `${vehicleName} · ${caseId} (${halfModel ? "half-model yaw 0°" : "full car"})`,
    casFile: casFiles[0] || "brak .cas",
    datFile: datFiles[0] || "brak .dat",
    solver: `${methods.fluentVersion ? "Fluent " + methods.fluentVersion : "Fluent (wersja nieodczytana)"}, ${
      halfModel ? "pół bolidu (symetria)" : "pełny bolid"
    }, yaw ${identity.yawDeg ?? 0}°`,
    turbulence: methods.turbulence || "nieodczytany",
    wallTreatment: mesh.scopedPrisms
      ? "scoped prisms (meshing)"
      : mesh.prismStairstepLocations != null
      ? `prisms (stairstep: ${mesh.prismStairstepLocations})`
      : "nieodczytana",
    cellsM,
    speedMs,
    yawDeg: Number(identity.yawDeg || 0),
    rho,
    mu,
    referenceAreaM2: frontalArea,
    referenceLengthM: wheelbaseM,
    iterations,
    residuals,
    yPlusWings,
    yPlusFloor,
    minOrthogonalQuality: num(mesh.minOrthogonalQuality),
    mrfFan: Boolean(methods.mrfFan),
    wheelsRotate: methods.wheelRotation ? Boolean(methods.wheelRotation.front && methods.wheelRotation.rear) : null,
    solverCrashes: (Array.isArray(methods.solverSessions) ? methods.solverSessions : [])
      .filter((session: { crashed?: boolean }) => session.crashed)
      .map((session: { file?: string; crashReasons?: string[] }) =>
        `${session.file}: ${(session.crashReasons || []).join(", ") || "BAD TERMINATION"}`,
      ),
    solverSessionCount: Array.isArray(methods.solverSessions) ? methods.solverSessions.length : 0,
    forcesSettled: typeof kpisRaw.convergence?.settled === "boolean" ? kpisRaw.convergence.settled : null,
    forceDriftReasons: Array.isArray(kpisRaw.convergence?.reasons) ? kpisRaw.convergence.reasons : [],
    iterationsLeft: num(kpisRaw.convergence?.iterationsLeft),
    plannedIterations: num(kpisRaw.convergence?.plannedIterations),
  }

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
    const shareDownforce = num(val.shareDownforcePct)
    const shareDrag = num(val.shareDragPct)
    components.push({
      name: groupNameLabels[key] || key.toUpperCase(),
      Cd: num(val.Cd),
      Cl: num(val.Cl),
      shareDownforcePct: shareDownforce == null ? null : Number(shareDownforce.toFixed(1)),
      shareDragPct: shareDrag == null ? null : Number(shareDrag.toFixed(1)),
    })
  }
  if (components.length === 0) {
    dataGaps.push("Brak sił po strefach.")
  }

  const qDyn = rho != null && speedMs != null ? 0.5 * rho * speedMs * speedMs : null
  const cdVal = num(kpisRaw.Cd) ?? num(kpisRaw.cx)
  const explicitCl = num(kpisRaw.Cl)
  const downforceFromPack = num(kpisRaw.downforceCoeff)
  const clVal = explicitCl ?? (downforceFromPack == null ? null : -downforceFromPack)
  const downforceCoeff = clVal == null ? null : Math.abs(clVal)
  const lOverD =
    num(kpisRaw.LOverD) ??
    (cdVal != null && downforceCoeff != null && cdVal !== 0 ? downforceCoeff / cdVal : null)

  const balanceRaw = kpisRaw.aeroBalance || {}
  const frontBalancePct = num(balanceRaw.frontPct)
  const balanceAxles =
    frontBalancePct == null
      ? null
      : { front: num(balanceRaw.frontDownforceCoeff), rear: num(balanceRaw.rearDownforceCoeff) }
  if (cdVal == null) dataGaps.push("Brak Cd.")
  if (clVal == null) dataGaps.push("Brak Cl.")
  if (frontBalancePct == null) {
    const missing: string[] = Array.isArray(balanceRaw.missing) ? balanceRaw.missing : []
    dataGaps.push(
      missing.length
        ? `Brak balansu przód/tył: ${missing.join(", ")}.`
        : "Brak balansu przód/tył (paczka nie ma kpis.aeroBalance).",
    )
  }

  const kpis: AeroKpis = {
    Cd: cdVal,
    Cl: clVal,
    Cs: num(kpisRaw.Cs),
    LOverD: lOverD,
    frontBalancePct,
    balanceAxles,
    downforceN:
      downforceCoeff != null && qDyn != null && frontalArea != null
        ? downforceCoeff * qDyn * frontalArea
        : null,
    dragN: cdVal != null && qDyn != null && frontalArea != null ? cdVal * qDyn * frontalArea : null,
    components,
  }

  const cadFiles = Array.isArray(files.cad) ? files.cad : []
  const cadModel: CadModel = {
    name: cadFiles[0] || (typeof vehicleYaml.name === "string" ? `${vehicleYaml.name}.STEP` : "brak CAD"),
    format: "STEP",
    triangles: null,
    wheelbaseMm,
    trackMm: num(vehicleYaml.trackMm),
    lengthMm: null,
    widthMm: null,
    heightMm: null,
    frontalAreaM2: frontalArea,
    rideHeightFrontMm: num(vehicleYaml.rideHeightFrontMm),
    rideHeightRearMm: num(vehicleYaml.rideHeightRearMm),
    rakeDeg: num(vehicleYaml.rakeDeg),
    components: components.map((c) => c.name),
  }
  if (cadModel.rideHeightFrontMm == null || cadModel.rideHeightRearMm == null) {
    dataGaps.push("Brak ride height w geometry.yaml.")
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
      component: typeof img.component === "string" ? img.component : undefined,
      feature: typeof img.feature === "string" ? img.feature : undefined,
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

  const reviewDevices: ReviewDevice[] = devices.map((device) => ({
    id: device.id,
    role: device.role,
    group: device.group,
  }))
  const review = evaluateCase(fluentCase, kpis, cadModel, images, reviewDevices)

  const checksum = kpisRaw.components?.checksum || kpisRaw.checksum
  if (checksum?.ok && num(checksum.cdRelErr) != null && num(checksum.clRelErr) != null) {
    review.findings.push({
      id: "force-checksum",
      severity: "info",
      title: "Suma sił stref jest spójna z globalnymi współczynnikami",
      evidence: `Błąd względny Cd: ${((checksum.cdRelErr as number) * 100).toFixed(3)}%, błąd Cl: ${((checksum.clRelErr as number) * 100).toFixed(3)}% (poniżej tolerancji 1%).`,
      recommendation: "Podział sił na komponenty jest zbilansowany numerycznie.",
    })
  } else if (checksum && checksum.ok === false) {
    review.findings.push({
      id: "force-checksum",
      severity: "issue",
      title: "Suma sił stref rozjeżdża się z Cd/Cl",
      evidence: "checksum.ok jest false. Udziały komponentów nie domykają się do współczynników globalnych.",
      recommendation: "Nie używaj podziału na FW/RW/podłogę, dopóki suma nie zejdzie poniżej 1%.",
    })
  }

  const reynoldsVal =
    rho != null && speedMs != null && wheelbaseM != null
      ? calcReynolds(rho, speedMs, wheelbaseM, mu ?? 1.789e-5)
      : null

  const prompt = [
    `# AeroPack v1 — recenzja case CFD Formula Student (${caseId})`,
    "",
    ...notesForAgent.map((n) => `- ${n}`),
    "",
    "## Luki danych",
    ...(dataGaps.length ? dataGaps.map((gap) => `- ${gap}`) : ["- brak"]),
    "",
    "## Identyfikacja i siatka",
    `- Bolid: ${vehicleName} (${halfModel ? "half-model yaw 0°" : "full-car"})`,
    `- Solver: ${fluentCase.solver}`,
    `- Siatka: ${fmt(cellsM, 2)} mln komórek, warstwa: ${fluentCase.wallTreatment}`,
    `- Przebieg: ${iterations ?? "brak"} iteracji, continuity ${residuals.continuity == null ? "brak" : residuals.continuity.toExponential(2)}`,
    "",
    "## Współczynniki aerodynamiki",
    `- Cd = ${fmt(cdVal, 3)}, Cl = ${fmt(clVal, 3)}, downforce coeff = ${fmt(downforceCoeff, 3)}`,
    `- L/D = ${fmt(lOverD, 2)}, balans przód = ${frontBalancePct == null ? "brak" : `${frontBalancePct}%`}`,
    `- Siły przy ${speedMs ?? "brak"} m/s: downforce ${fmt(kpis.downforceN, 0)} N, drag ${fmt(kpis.dragN, 0)} N`,
    "",
    "## Udział komponentów",
    ...(components.length
      ? components.map(
          (c) =>
            `- ${c.name}: DF share ${fmt(c.shareDownforcePct, 1, "%")}, Drag share ${fmt(c.shareDragPct, 1, "%")}, Cl ${fmt(c.Cl, 2)}, Cd ${fmt(c.Cd, 2)}`,
        )
      : ["- brak podziału na strefy"]),
    "",
    `## Klatki post-processingu (${images.filter((i) => i.hero).length} hero do wglądu)`,
    ...images
      .filter((i) => i.hero)
      .slice(0, 20)
      .map((h) => `- [HERO] ${h.filename} (${h.axis}, ${h.field}${h.stationM != null ? `, stacja ${h.stationM}m` : ""})`),
    "",
    "Puste pola zostają puste. Nie uzupełniaj ich liczbami z innego case'a ani z pikseli.",
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
    dataGaps,
    rawPack: raw,
    prompt,
  }
}
