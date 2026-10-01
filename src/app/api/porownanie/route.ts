import { NextResponse } from "next/server"
import fs from "fs/promises"
import path from "path"

/**
 * The comparison page made by `python -m ingest compare` (default folder `quant/porownanie`).
 * Only that one file is served, so the request carries no path.
 */
export async function GET() {
  const file = path.join(process.cwd(), "quant", "porownanie", "POROWNANIE.html")
  try {
    const html = await fs.readFile(file, "utf-8")
    return new NextResponse(html, {
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-cache",
        "X-Content-Type-Options": "nosniff",
      },
    })
  } catch {
    return NextResponse.json(
      { ok: false, error: "Brak porównania. Zrób je poleceniem: python -m ingest compare <folder1> <folder2>" },
      { status: 404 },
    )
  }
}
