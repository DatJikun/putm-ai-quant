import fs from "fs/promises"
import path from "path"
import { summarizeMeta } from "./meta"
import { packsRoot } from "./pack-path"

export type PackListEntry = {
  id: string
  name: string
  vehicle: string
  generatedAt?: string
  cells: number
  imagesTotal: number
  heroCount: number
  warningsCount: number
  isLocal: true
  verdict: string | null
  credibilityScore: number | null
  findingsCount: number
  hasMeta: boolean
}

type Rec = Record<string, unknown>

function rec(value: unknown): Rec {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? (value as Rec) : {}
}

async function readJson(file: string): Promise<unknown> {
  try {
    return JSON.parse(await fs.readFile(file, "utf-8"))
  } catch {
    return null
  }
}

/** Every folder under `root` that holds a readable `aeropack.json`, with what the meta pack says about it. */
export async function listPacks(root: string = packsRoot()): Promise<PackListEntry[]> {
  let entries: import("fs").Dirent[]
  try {
    entries = await fs.readdir(root, { withFileTypes: true })
  } catch {
    return []
  }
  const packs: PackListEntry[] = []
  for (const entry of entries) {
    if (!entry.isDirectory()) continue
    const raw = await readJson(path.join(root, entry.name, "aeropack.json"))
    if (raw === null || typeof raw !== "object") continue
    const pack = rec(raw)
    const identity = rec(pack.identity)
    const images = rec(pack.images)
    const meta = summarizeMeta(await readJson(path.join(root, entry.name, "meta", "meta.json")))
    packs.push({
      id: entry.name,
      name: `${identity.vehicle || "Aero"} · ${identity.caseId || entry.name}`,
      vehicle: String(identity.vehicle || "PM09"),
      generatedAt: typeof pack.generatedAt === "string" ? pack.generatedAt : undefined,
      cells: Number(rec(pack.mesh).cells) || 0,
      imagesTotal: Number(images.total) || 0,
      heroCount: Array.isArray(images.hero) ? images.hero.length : 0,
      warningsCount: Array.isArray(pack.warnings) ? pack.warnings.length : 0,
      isLocal: true,
      verdict: meta?.verdict ?? null,
      credibilityScore: meta?.credibility?.score ?? null,
      findingsCount: meta?.findings.length ?? 0,
      hasMeta: meta !== null,
    })
  }
  return packs
}
