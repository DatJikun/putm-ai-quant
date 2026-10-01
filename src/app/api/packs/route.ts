import { NextRequest, NextResponse } from "next/server"
import fs from "fs/promises"
import path from "path"
import { resolvePackDir } from "@/lib/pack-path"
import { listPacks } from "@/lib/pack-list"
import { parseGallery, summarizeMeta } from "@/lib/meta"

type Rec = Record<string, unknown>

function rec(value: unknown): Rec {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? (value as Rec) : {}
}

async function readIfPresent(file: string): Promise<string | null> {
  try {
    return await fs.readFile(file, "utf-8")
  } catch {
    return null
  }
}

/** Frames from `images/index.json`; null when the file is missing or not valid JSON. */
async function readImagesIndex(packFolder: string): Promise<unknown[] | null> {
  const raw = await readIfPresent(path.join(packFolder, "images", "index.json"))
  if (raw === null) return null
  try {
    const index = rec(JSON.parse(raw)).index
    return Array.isArray(index) ? index : []
  } catch {
    return null
  }
}

/** Parsed JSON of a file in the pack; null when it is missing or not valid JSON. */
async function readJson(file: string): Promise<unknown> {
  const raw = await readIfPresent(file)
  if (raw === null) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const id = searchParams.get("id")

    // If a specific pack ID is requested, return its full data
    if (id) {
      const packFolder = resolvePackDir(id)
      if (!packFolder) {
        return NextResponse.json({ ok: false, error: "niepoprawne id packa" }, { status: 400 })
      }

      const rawContent = await readIfPresent(path.join(packFolder, "aeropack.json"))
      if (rawContent === null) {
        return NextResponse.json(
          { ok: false, error: `Nie znaleziono packa '${id}' na dysku.` },
          { status: 404 },
        )
      }
      let pack: Rec
      try {
        pack = rec(JSON.parse(rawContent))
      } catch {
        return NextResponse.json(
          { ok: false, error: `Pack '${id}' ma uszkodzony aeropack.json.` },
          { status: 422 },
        )
      }

      // Without an images index the hero frames stored in the pack itself are used
      const hero = rec(pack.images).hero
      const imagesList = (await readImagesIndex(packFolder)) ?? (Array.isArray(hero) ? hero : [])

      const geometryYaml = (await readIfPresent(path.join(packFolder, "geometry.yaml"))) ?? ""

      // The meta pack and the gallery are optional: older packs have neither
      const meta = summarizeMeta(await readJson(path.join(packFolder, "meta", "meta.json")))
      const gallery = parseGallery(await readJson(path.join(packFolder, "obrazy", "index.json")))

      return NextResponse.json({
        ok: true,
        id,
        pack,
        images: imagesList,
        geometryYaml,
        meta,
        gallery,
      })
    }

    // Otherwise, list all available packs
    return NextResponse.json({ ok: true, packs: await listPacks() })
  } catch (err) {
    console.error("/api/packs:", err)
    return NextResponse.json({ ok: false, error: "błąd serwera" }, { status: 500 })
  }
}
