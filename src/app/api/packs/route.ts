import { NextRequest, NextResponse } from "next/server"
import fs from "fs/promises"
import path from "path"
import { packsRoot, resolvePackDir } from "@/lib/pack-path"

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

      return NextResponse.json({
        ok: true,
        id,
        pack,
        images: imagesList,
        geometryYaml,
      })
    }

    // Otherwise, list all available packs
    const packsDir = packsRoot()
    let entries: import("fs").Dirent[]
    try {
      entries = await fs.readdir(packsDir, { withFileTypes: true })
    } catch {
      return NextResponse.json({ ok: true, packs: [] })
    }
    const packs = []

    for (const entry of entries) {
      if (!entry.isDirectory()) continue
      const rawContent = await readIfPresent(path.join(packsDir, entry.name, "aeropack.json"))
      if (rawContent === null) continue
      try {
        const pack = rec(JSON.parse(rawContent))
        const identity = rec(pack.identity)
        const images = rec(pack.images)
        packs.push({
          id: entry.name,
          name: `${identity.vehicle || "Aero"} · ${identity.caseId || entry.name}`,
          vehicle: identity.vehicle || "PM09",
          generatedAt: pack.generatedAt,
          cells: rec(pack.mesh).cells || 0,
          imagesTotal: images.total || 0,
          heroCount: Array.isArray(images.hero) ? images.hero.length : 0,
          warningsCount: Array.isArray(pack.warnings) ? pack.warnings.length : 0,
          isLocal: true,
        })
      } catch {
        // Skip packs whose aeropack.json is not valid JSON
      }
    }

    return NextResponse.json({
      ok: true,
      packs,
    })
  } catch (err) {
    console.error("/api/packs:", err)
    return NextResponse.json({ ok: false, error: "błąd serwera" }, { status: 500 })
  }
}
