import assert from "node:assert/strict"
import fs from "node:fs/promises"
import path from "node:path"
import { test } from "node:test"
import { answer, type AskArgs, type PackReader } from "../src/lib/ask"

const FIXTURES = path.join(__dirname, "fixtures")

type Case = {
  name: string
  pack?: string
  tool: string
  args: AskArgs
  expect?: Record<string, unknown>
  error?: string
}

function readerFor(folder: string): PackReader {
  return async (file) => {
    try {
      return await fs.readFile(path.join(folder, file), "utf-8")
    } catch (err) {
      if ((err as NodeJS.ErrnoException).code === "ENOENT") return null
      throw err
    }
  }
}

async function loadCases(): Promise<Case[]> {
  return JSON.parse(await fs.readFile(path.join(FIXTURES, "ask-pack", "cases.json"), "utf-8"))
}

test("ask answers match the cases shared with ingest/ask.py", async () => {
  const cases = await loadCases()
  assert.ok(cases.length > 0)
  for (const item of cases) {
    const result = await answer(readerFor(path.join(FIXTURES, item.pack ?? "ask-pack")), item.tool, item.args)
    if (item.error !== undefined) {
      assert.equal(result.ok, false, item.name)
      if (!result.ok) assert.equal(result.error, item.error, item.name)
    } else {
      assert.equal(result.ok, true, item.name)
      if (result.ok) assert.deepEqual(result.data, item.expect, item.name)
    }
  }
})

test("ask errors carry an HTTP status the route can return", async () => {
  const read = readerFor(path.join(FIXTURES, "ask-empty"))
  const missing = await answer(read, "forces", {})
  assert.deepEqual(missing, { ok: false, status: 404, error: "brak aeropack.json" })
  const unknown = await answer(read, "bogus", {})
  assert.deepEqual(unknown, { ok: false, status: 400, error: "nieznane pytanie: bogus" })
  const noPart = await answer(read, "part", { part: " " })
  assert.deepEqual(noPart, { ok: false, status: 400, error: "brak nazwy części" })
})
