import { NextRequest, NextResponse } from "next/server"
import fs from "fs/promises"
import path from "path"

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const id = searchParams.get("id")
    const packsDir = path.join(process.cwd(), "packs")

    // If a specific pack ID is requested, return its full data
    if (id) {
      // Prevent directory traversal
      const safeId = path.basename(id)
      const packFolder = path.join(packsDir, safeId)
      const aeropackPath = path.join(packFolder, "aeropack.json")

      try {
        const rawContent = await fs.readFile(aeropackPath, "utf-8")
        const pack = JSON.parse(rawContent)

        // Try reading images index
        let imagesList: any[] = []
        try {
          const indexPath = path.join(packFolder, "images", "index.json")
          const indexRaw = await fs.readFile(indexPath, "utf-8")
          const parsedIndex = JSON.parse(indexRaw)
          imagesList = parsedIndex.index || []
        } catch {
          imagesList = pack.images?.hero || []
        }

        // Try reading geometry.yaml
        let geometryYaml = ""
        try {
          const geomPath = path.join(packFolder, "geometry.yaml")
          geometryYaml = await fs.readFile(geomPath, "utf-8")
        } catch {
          // ignore if missing
        }

        return NextResponse.json({
          ok: true,
          id: safeId,
          pack,
          images: imagesList,
          geometryYaml,
        })
      } catch (err: any) {
        return NextResponse.json(
          { ok: false, error: `Nie znaleziono packa '${safeId}' na dysku: ${err.message}` },
          { status: 404 }
        )
      }
    }

    // Otherwise, list all available packs
    const entries = await fs.readdir(packsDir, { withFileTypes: true })
    const packs = []

    for (const entry of entries) {
      if (entry.isDirectory()) {
        const aeropackPath = path.join(packsDir, entry.name, "aeropack.json")
        try {
          const stat = await fs.stat(aeropackPath)
          if (stat.isFile()) {
            const rawContent = await fs.readFile(aeropackPath, "utf-8")
            const pack = JSON.parse(rawContent)
            packs.push({
              id: entry.name,
              name: `${pack.identity?.vehicle || "Aero"} · ${pack.identity?.caseId || entry.name}`,
              vehicle: pack.identity?.vehicle || "PM09",
              generatedAt: pack.generatedAt,
              cells: pack.mesh?.cells || 0,
              imagesTotal: pack.images?.total || 0,
              heroCount: Array.isArray(pack.images?.hero) ? pack.images.hero.length : 0,
              warningsCount: Array.isArray(pack.warnings) ? pack.warnings.length : 0,
              isLocal: true,
            })
          }
        } catch {
          // Skip if aeropack.json doesn't exist
        }
      }
    }

    return NextResponse.json({
      ok: true,
      packs,
    })
  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 })
  }
}
