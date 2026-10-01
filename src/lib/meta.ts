/**
 * What the workbench needs from `meta/meta.json` and the picture gallery of a pack.
 * `meta.json` is large (it holds the whole report), so the server sends this summary only.
 */
import type { Axis, FieldId } from "./types"

export type FindingWeight = "wysoka" | "srednia" | "niska" | "info"
export type CheckStatus = "ok" | "uwaga" | "zle" | "brak"

export type MetaFinding = { id: string; weight: FindingWeight; text: string; evidence: string }

export type MetaCheck = {
  id: string
  title: string
  status: CheckStatus
  weight: number
  value: string
  detail: string
  sources: string[]
}

export type MetaCredibility = {
  score: number | null
  coverage: number | null
  label: string
  byCategory: Record<string, number | null>
  checks: MetaCheck[]
  unknown: string[]
}

export type MetaProvenance = { name: string; source: string; method: string; accuracy: string }

export type MetaSummary = {
  caseId: string | null
  verdict: string | null
  findings: MetaFinding[]
  credibility: MetaCredibility | null
  provenance: MetaProvenance[]
  originalsBytes: number | null
  metaBytes: number | null
}

export type Gallery = {
  planes: Partial<Record<"x" | "y" | "z", number[]>>
  fields: string[]
  surface: string[]
}

type Rec = Record<string, unknown>

const WEIGHTS: readonly FindingWeight[] = ["wysoka", "srednia", "niska", "info"]
const STATUSES: readonly CheckStatus[] = ["ok", "uwaga", "zle", "brak"]

function rec(value: unknown): Rec {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? (value as Rec) : {}
}

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function str(value: unknown): string {
  return typeof value === "string" ? value : ""
}

function strList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : []
}

/** The summary of a parsed `meta.json`, or null when it is not one. */
export function summarizeMeta(raw: unknown): MetaSummary | null {
  const meta = rec(raw)
  if (typeof meta.schemat !== "string" || !meta.schemat.startsWith("aeropack-meta/")) return null
  const findings: MetaFinding[] = []
  for (const item of Array.isArray(meta.wnioski) ? meta.wnioski : []) {
    const f = rec(item)
    const weight = WEIGHTS.find((w) => w === f.waga)
    if (weight && typeof f.tekst === "string") {
      findings.push({ id: str(f.id), weight, text: f.tekst, evidence: str(f.dowod) })
    }
  }
  let credibility: MetaCredibility | null = null
  const cred = rec(meta.wiarygodnosc)
  if (Object.keys(cred).length > 0) {
    const checks: MetaCheck[] = []
    for (const item of Array.isArray(cred.checks) ? cred.checks : []) {
      const c = rec(item)
      const status = STATUSES.find((s) => s === c.status)
      if (status) {
        checks.push({
          id: str(c.id),
          title: str(c.title),
          status,
          weight: num(c.weight) ?? 0,
          value: str(c.value),
          detail: str(c.detail),
          sources: strList(c.sources),
        })
      }
    }
    const byCategory: Record<string, number | null> = {}
    for (const [name, value] of Object.entries(rec(cred.byCategory))) byCategory[name] = num(value)
    credibility = {
      score: num(cred.score),
      coverage: num(cred.coverage),
      label: str(cred.label),
      byCategory,
      checks,
      unknown: strList(cred.unknown),
    }
  }
  const provenance: MetaProvenance[] = Object.entries(rec(meta.zrodla)).map(([name, value]) => {
    const p = rec(value)
    return { name, source: str(p.zrodlo), method: str(p.metoda), accuracy: str(p.dokladnosc) }
  })
  let metaBytes = 0
  const maps = rec(meta.mapy)
  for (const info of Object.values(rec(maps.powierzchnia))) metaBytes += num(rec(info).bajty) ?? 0
  metaBytes += num(rec(maps.przekroje).bajty) ?? 0
  return {
    caseId: typeof meta.caseId === "string" ? meta.caseId : null,
    verdict: str(rec(meta.werdykt).label) || null,
    findings,
    credibility,
    provenance,
    originalsBytes: num(rec(meta.oryginaly).bajtyRazem),
    metaBytes: metaBytes > 0 ? metaBytes : null,
  }
}

/** The gallery description of `obrazy/index.json`, or null when it is not one. */
export function parseGallery(raw: unknown): Gallery | null {
  const index = rec(raw)
  const positions = rec(index.positions)
  const planes: Gallery["planes"] = {}
  for (const axis of ["x", "y", "z"] as const) {
    const values = Array.isArray(positions[axis]) ? positions[axis].filter((v): v is number => num(v) !== null) : []
    if (values.length > 0) planes[axis] = values
  }
  if (Object.keys(planes).length === 0) return null
  return { planes, fields: strList(index.fields), surface: strList(index.surface) }
}

/** The plane position closest to `station`, or null when the list is empty. */
export function nearestPlane(positions: readonly number[], station: number): number | null {
  let best: number | null = null
  for (const p of positions) {
    if (best === null || Math.abs(p - station) < Math.abs(best - station)) best = p
  }
  return best
}

const GALLERY_FIELD: Partial<Record<FieldId, string>> = { cp: "cp", cpt: "cpt", pt: "cpt", vel: "vel", u: "vel" }
const SURFACE_FIELD: Partial<Record<FieldId, string>> = { cp: "cp", yplus: "yplus" }

export function packFileUrl(packId: string, relative: string): string {
  return `/api/packs/files/${encodeURIComponent(packId)}/${relative.split("/").map(encodeURIComponent).join("/")}`
}

/** Our own picture for a CFD-Post frame: a plane at the nearest position, or a wall view for full-car frames. */
export function frameImageUrl(
  packId: string,
  gallery: Gallery | null,
  axis: Axis,
  field: FieldId,
  stationM: number | null,
  camera = "",
): string | null {
  if (!gallery) return null
  if (axis === "full") {
    const surface = SURFACE_FIELD[field]
    if (!surface) return null
    const view = /g[oó]r|top/i.test(camera) ? "z-gory" : /prz|front/i.test(camera) ? "z-przodu" : "z-boku"
    const name = `${surface}_${view}.png`
    return gallery.surface.includes(name) ? packFileUrl(packId, `obrazy/powierzchnia/${name}`) : null
  }
  const mapped = GALLERY_FIELD[field]
  const positions = gallery.planes[axis]
  if (!mapped || !positions || stationM === null || !gallery.fields.includes(mapped)) return null
  const pos = nearestPlane(positions, stationM)
  return pos === null ? null : packFileUrl(packId, `obrazy/przekroje/${axis}/${mapped}/${axis}_${pos.toFixed(3)}.png`)
}

export const WEIGHT_LABEL: Record<FindingWeight, string> = {
  wysoka: "ważne",
  srednia: "uwaga",
  niska: "drobne",
  info: "informacja",
}

export const STATUS_LABEL: Record<CheckStatus, string> = {
  ok: "OK",
  uwaga: "UWAGA",
  zle: "ŹLE",
  brak: "BRAK DANYCH",
}

export function megabytes(bytes: number | null): string {
  if (bytes === null) return "brak"
  return bytes >= 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : `${(bytes / 1e6).toFixed(bytes < 1e7 ? 1 : 0)} MB`
}
