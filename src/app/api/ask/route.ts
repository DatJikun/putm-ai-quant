import { NextRequest, NextResponse } from "next/server"
import fs from "fs/promises"
import path from "path"
import { answer, type PackReader } from "@/lib/ask"
import { resolvePackDir } from "@/lib/pack-path"

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url)
  const packDir = resolvePackDir(searchParams.get("id"))
  if (!packDir) {
    return NextResponse.json({ ok: false, error: "brak albo niepoprawne id paczki" }, { status: 400 })
  }

  const read: PackReader = async (file) => {
    try {
      return await fs.readFile(path.join(packDir, file), "utf-8")
    } catch (err) {
      if ((err as NodeJS.ErrnoException).code === "ENOENT") return null
      throw err
    }
  }

  try {
    const result = await answer(read, searchParams.get("tool") || "forces", {
      part: searchParams.get("part"),
      device: searchParams.get("device"),
      axis: searchParams.get("axis"),
      station: searchParams.get("station"),
      field: searchParams.get("field"),
    })
    if (!result.ok) {
      return NextResponse.json({ ok: false, error: result.error }, { status: result.status })
    }
    return NextResponse.json({ ok: true, ...result.data })
  } catch {
    return NextResponse.json({ ok: false, error: "nie udało się odczytać paczki" }, { status: 500 })
  }
}
