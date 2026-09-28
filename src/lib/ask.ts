/**
 * One answer from a pack folder. Port of `ingest/ask.py`: both read the same
 * fixtures in `tests/fixtures/ask-pack` and must give the same answers, so change
 * them together.
 */

import { parseGeometryYaml } from "./geometry-yaml"

type Rec = Record<string, unknown>

export type AskArgs = {
  part?: string | null
  name?: string | null
  device?: string | null
  axis?: string | null
  station?: number | string | null
  station_m?: number | string | null
  field?: string | null
}

export type AskResult =
  | { ok: true; data: Rec }
  | { ok: false; status: number; error: string }

export type PackFile = "aeropack.json" | "profile.json" | "images/index.json" | "geometry.yaml"

/** Text of a file in the pack folder, or null when the file is missing. */
export type PackReader = (file: PackFile) => Promise<string | null>

/** Parsed JSON of a pack file. Missing file gives null; broken JSON throws. */
async function readJson(read: PackReader, file: PackFile): Promise<unknown | null> {
  const text = await read(file)
  return text === null ? null : JSON.parse(text)
}

function rec(value: unknown): Rec {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? (value as Rec) : {}
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function fail(status: number, error: string): AskResult {
  return { ok: false, status, error }
}

async function forces(read: PackReader): Promise<AskResult> {
  const raw = await readJson(read, "aeropack.json")
  if (raw == null) return fail(404, "brak aeropack.json")
  const pack = rec(raw)
  const kpis = rec(pack.kpis)
  return {
    ok: true,
    data: {
      case: rec(pack.identity).caseId ?? null,
      cd: kpis.Cd ?? null,
      cl: kpis.Cl ?? null,
      ld: kpis.LOverD ?? null,
      cm: kpis.cm ?? null,
      cz: kpis.cz ?? null,
      komponenty: rec(rec(kpis.components).groups),
    },
  }
}

async function part(read: PackReader, name: string): Promise<AskResult> {
  const key = name.trim().toLowerCase()
  if (!key) return fail(400, "brak nazwy części")
  const raw = await readJson(read, "profile.json")
  if (raw == null) return fail(404, "brak profile.json (python -m ingest profiles FOLDER_CASE --out packs/ID/profile.json)")
  for (const item of list(rec(raw).skrzydla)) {
    const wing = rec(item)
    if (wing.id !== key && !String(wing.nazwa ?? "").toLowerCase().includes(key)) continue
    const przekroje = list(wing.przekroje).map((entry) => {
      const cut = rec(entry)
      if ("dol" in cut) {
        return {
          y_m: cut.y_m ?? null,
          dol: rec(cut.dol).podsumowanie ?? null,
          gora: rec(cut.gora).podsumowanie ?? null,
        }
      }
      return { y_m: cut.y_m ?? null, podsumowanie: cut.podsumowanie ?? null }
    })
    return { ok: true, data: { id: wing.id ?? null, nazwa: wing.nazwa ?? null, przekroje } }
  }
  return fail(404, `brak części ${name}`)
}

async function device(read: PackReader, name: string): Promise<AskResult> {
  const text = await read("geometry.yaml")
  if (text === null) return fail(404, "brak geometry.yaml (python -m ingest pack FOLDER_CASE --out packs/ID)")
  const cards = parseGeometryYaml(text)
  const key = name.trim().toLowerCase()
  if (!key) {
    return {
      ok: true,
      data: {
        urzadzenia: cards.map((card) => ({ id: card.id, group: card.group ?? null, role: card.role ?? null })),
      },
    }
  }
  const card = cards.find((item) => item.id.toLowerCase() === key)
  if (!card) {
    return fail(404, `brak urządzenia ${name} (dostępne: ${cards.map((item) => item.id).join(", ")})`)
  }
  return { ok: true, data: card as unknown as Rec }
}

async function sliceFrame(
  read: PackReader,
  axis: string,
  station: number,
  field: string | null,
): Promise<AskResult> {
  const raw = await readJson(read, "images/index.json")
  let best: Rec | null = null
  let bestDist: number | null = null
  for (const item of list(rec(raw).index)) {
    const row = rec(item)
    if (row.axis !== axis) continue
    if (field && row.field !== field) continue
    if (row.stationM == null) continue
    const dist = Math.abs(Number(row.stationM) - station)
    if (bestDist === null || dist < bestDist) {
      best = row
      bestDist = dist
    }
  }
  if (best === null) return fail(404, "brak klatki dla tej stacji")
  return {
    ok: true,
    data: {
      plik: best.filename ?? best.file ?? null,
      os: best.axis ?? null,
      pole: best.field ?? null,
      stacja_m: best.stationM ?? null,
      czesci: list(best.onCar),
    },
  }
}

export async function answer(read: PackReader, tool: string, args: AskArgs): Promise<AskResult> {
  if (tool === "get_forces" || tool === "forces") return forces(read)
  if (tool === "get_part" || tool === "part") return part(read, String(args.part || args.name || ""))
  if (tool === "get_device" || tool === "device") return device(read, String(args.device || ""))
  if (tool === "get_slice" || tool === "slice") {
    const station = Number(args.station || args.station_m || 0)
    if (!Number.isFinite(station)) return fail(400, "station musi być liczbą")
    return sliceFrame(read, String(args.axis || "x"), station, args.field ? String(args.field) : null)
  }
  return fail(400, `nieznane pytanie: ${tool}`)
}
