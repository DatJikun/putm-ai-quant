import { NextResponse } from "next/server"
import fs from "fs/promises"
import { contentTypeFor, resolvePackFile } from "@/lib/pack-path"

/**
 * One file of a pack: the summary pages, the gallery and its pictures, `meta.json`.
 * The path is part of the URL (not a query), so the relative links inside `galeria.html`
 * keep working. Only files on the list in `resolvePackFile` are served.
 */
export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string; path: string[] }> },
) {
  const { id, path: segments } = await context.params
  const file = resolvePackFile(decodeURIComponent(id), segments.map((s) => decodeURIComponent(s)))
  if (!file) {
    return NextResponse.json({ ok: false, error: "plik niedostępny" }, { status: 404 })
  }
  try {
    const bytes = await fs.readFile(file)
    return new NextResponse(new Uint8Array(bytes), {
      headers: {
        "Content-Type": contentTypeFor(file),
        "Cache-Control": "no-cache",
        "X-Content-Type-Options": "nosniff",
      },
    })
  } catch {
    return NextResponse.json({ ok: false, error: "nie ma takiego pliku" }, { status: 404 })
  }
}
