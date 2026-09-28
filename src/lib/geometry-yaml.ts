import { parse } from "yaml"

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

type Rec = Record<string, unknown>

function rec(value: unknown): Rec {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? (value as Rec) : {}
}

/** `TBD` and empty values mean "not measured yet". Same rule as ingest/ask.py. */
function fillGaps(value: unknown): unknown {
  if (value === "TBD" || value === "") return null
  if (Array.isArray(value)) return value.map(fillGaps)
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, fillGaps(item)]))
  }
  return value
}

function load(text: string | undefined): Rec {
  if (!text) return {}
  try {
    return rec(parse(text))
  } catch {
    return {}
  }
}

export function parseVehicleYaml(yamlStr?: string): Record<string, string | number | boolean | null> {
  const vehicle: Record<string, string | number | boolean | null> = {}
  for (const [key, value] of Object.entries(rec(load(yamlStr).vehicle))) {
    const item = fillGaps(value)
    if (item === null || ["string", "number", "boolean"].includes(typeof item)) {
      vehicle[key] = item as string | number | boolean | null
    }
  }
  return vehicle
}

export function parseGeometryYaml(yamlStr?: string): AeroDevice[] {
  const devices = load(yamlStr).devices
  if (!Array.isArray(devices)) return []
  return devices
    .map((device) => rec(fillGaps(device)))
    .filter((device): device is Rec & { id: string } => typeof device.id === "string" && device.id !== "")
    .map((device) => device as AeroDevice)
}
