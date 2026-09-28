import assert from "node:assert/strict"
import path from "node:path"
import { test } from "node:test"
import { packsRoot, resolvePackDir } from "../src/lib/pack-path"

test("pack ids that are plain folder names resolve under packs/", () => {
  const root = path.join(process.cwd(), "packs")
  assert.equal(packsRoot(), root)
  assert.equal(resolvePackDir("BASELINEiter002"), path.join(root, "BASELINEiter002"))
  assert.equal(resolvePackDir("PM09 baseline 2"), path.join(root, "PM09 baseline 2"))
  assert.equal(resolvePackDir("case-1.v2"), path.join(root, "case-1.v2"))
})

test("pack ids that could leave packs/ are refused", () => {
  for (const id of ["..", ".", "", "../x", "a/b", "/etc/passwd", "packs/..", "x\0y", "..//"]) {
    assert.equal(resolvePackDir(id), null, JSON.stringify(id))
  }
  assert.equal(resolvePackDir(null), null)
  assert.equal(resolvePackDir(undefined), null)
})
