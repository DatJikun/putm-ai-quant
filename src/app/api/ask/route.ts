import { NextRequest, NextResponse } from "next/server"
import fs from "fs/promises"
import path from "path"

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url)
  const id = path.basename(searchParams.get("id") || "")
  const tool = searchParams.get("tool") || "forces"
  if (!id) {
    return NextResponse.json({ ok: false, error: "brak id paczki" }, { status: 400 })
  }
  const packDir = path.join(process.cwd(), "packs", id)

  try {
    if (tool === "forces") {
      const raw = await fs.readFile(path.join(packDir, "aeropack.json"), "utf-8")
      const pack = JSON.parse(raw)
      const kpis = pack.kpis || {}
      return NextResponse.json({
        ok: true,
        case: pack.identity?.caseId,
        cd: kpis.Cd,
        cl: kpis.Cl,
        ld: kpis.LOverD,
        cm: kpis.cm,
        cz: kpis.cz,
        komponenty: kpis.components?.groups || {},
      })
    }
    if (tool === "part") {
      const part = (searchParams.get("part") || "").toLowerCase()
      const raw = await fs.readFile(path.join(packDir, "profile.json"), "utf-8")
      const doc = JSON.parse(raw)
      const wing = (doc.skrzydla || []).find((item: { id?: string }) => item.id === part)
      if (!wing) {
        return NextResponse.json({ ok: false, error: "brak części" }, { status: 404 })
      }
      const przekroje = (wing.przekroje || []).map((cut: { y_m?: number; dol?: { podsumowanie?: unknown }; gora?: { podsumowanie?: unknown }; podsumowanie?: unknown }) => ({
        y_m: cut.y_m,
        dol: cut.dol?.podsumowanie,
        gora: cut.gora?.podsumowanie,
        podsumowanie: cut.podsumowanie,
      }))
      return NextResponse.json({ ok: true, id: wing.id, nazwa: wing.nazwa, przekroje })
    }
    if (tool === "slice") {
      const axis = searchParams.get("axis") || "x"
      const station = Number(searchParams.get("station") || "0")
      const field = searchParams.get("field")
      const raw = await fs.readFile(path.join(packDir, "images", "index.json"), "utf-8")
      const rows = JSON.parse(raw).index || []
      let best: { filename?: string; axis?: string; field?: string; stationM?: number; onCar?: string[] } | null = null
      let bestDist = Infinity
      for (const row of rows) {
        if (row.axis !== axis || row.stationM == null) continue
        if (field && row.field !== field) continue
        const dist = Math.abs(row.stationM - station)
        if (dist < bestDist) {
          best = row
          bestDist = dist
        }
      }
      if (!best) {
        return NextResponse.json({ ok: false, error: "brak klatki" }, { status: 404 })
      }
      return NextResponse.json({
        ok: true,
        plik: best.filename,
        os: best.axis,
        pole: best.field,
        stacja_m: best.stationM,
        czesci: best.onCar || [],
      })
    }
    return NextResponse.json({ ok: false, error: "nieznane pytanie" }, { status: 400 })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "błąd odczytu"
    return NextResponse.json({ ok: false, error: message }, { status: 404 })
  }
}
