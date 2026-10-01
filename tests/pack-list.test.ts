import assert from "node:assert/strict"
import fs from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import { test } from "node:test"
import { listPacks } from "../src/lib/pack-list"

async function makeRoot() {
  return fs.mkdtemp(path.join(os.tmpdir(), "packs-"))
}

async function writePack(root: string, name: string, pack: unknown, meta?: unknown) {
  await fs.mkdir(path.join(root, name, "meta"), { recursive: true })
  await fs.writeFile(path.join(root, name, "aeropack.json"), JSON.stringify(pack))
  if (meta !== undefined) await fs.writeFile(path.join(root, name, "meta", "meta.json"), JSON.stringify(meta))
}

test("a folder with a pack and a meta pack is listed with the verdict and the grade", async () => {
  const root = await makeRoot()
  await writePack(
    root,
    "A",
    { identity: { vehicle: "PM09", caseId: "C1" }, mesh: { cells: 5 }, images: { total: 3, hero: [1, 2] }, warnings: ["x"] },
    {
      schemat: "aeropack-meta/v1",
      werdykt: { label: "Wyniki orientacyjne" },
      wnioski: [{ id: "a", waga: "wysoka", tekst: "t", dowod: "d" }],
      wiarygodnosc: { score: 83, checks: [] },
    },
  )
  const [pack] = await listPacks(root)
  assert.equal(pack.id, "A")
  assert.equal(pack.name, "PM09 · C1")
  assert.equal(pack.cells, 5)
  assert.equal(pack.heroCount, 2)
  assert.equal(pack.warningsCount, 1)
  assert.equal(pack.verdict, "Wyniki orientacyjne")
  assert.equal(pack.credibilityScore, 83)
  assert.equal(pack.findingsCount, 1)
  assert.equal(pack.hasMeta, true)
})

test("an older pack without a meta pack is still listed", async () => {
  const root = await makeRoot()
  await writePack(root, "Old", { identity: {} })
  const [pack] = await listPacks(root)
  assert.equal(pack.name, "Aero · Old")
  assert.equal(pack.hasMeta, false)
  assert.equal(pack.verdict, null)
  assert.equal(pack.credibilityScore, null)
})

test("folders without a readable aeropack.json, and plain files, are skipped", async () => {
  const root = await makeRoot()
  await fs.mkdir(path.join(root, "empty"))
  await fs.mkdir(path.join(root, "broken"))
  await fs.writeFile(path.join(root, "broken", "aeropack.json"), "{nie json")
  await fs.writeFile(path.join(root, "plik.txt"), "x")
  assert.deepEqual(await listPacks(root), [])
  assert.deepEqual(await listPacks(path.join(root, "nie-ma-takiego")), [])
})
