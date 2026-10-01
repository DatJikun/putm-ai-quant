import assert from "node:assert/strict"
import path from "node:path"
import { test } from "node:test"
import { contentTypeFor, packsRoot, resolvePackDir, resolvePackFile } from "../src/lib/pack-path"

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

test("only the listed files of a pack can be served", () => {
  const dir = path.join(packsRoot(), "P1")
  const ok = [
    ["SKROT.html"],
    ["PELNY.md"],
    ["WIARYGODNOSC.md"],
    ["dla-chatbota.md"],
    ["meta", "meta.json"],
    ["obrazy", "galeria.html"],
    ["obrazy", "przekroje", "x", "cp", "x_-1.100.png"],
    ["obrazy", "powierzchnia", "cp_z-boku.png"],
  ]
  for (const segments of ok) {
    assert.equal(resolvePackFile("P1", segments), path.join(dir, ...segments), segments.join("/"))
  }
  const refused = [
    ["aeropack.json"],
    ["meta", "powierzchnia_3mm.npz"],
    ["obrazy", "przekroje", "x", "cp", "x.exe"],
    ["obrazy", "..", "aeropack.json"],
    ["..", "BASELINE", "aeropack.json"],
    ["obrazy", "przekroje", "..", "..", "aeropack.json"],
    ["SKROT.html", "x"],
    ["obrazy/galeria.html"],
    ["obrazy\galeria.html"],
    ["obrazy", ".", "galeria.html"],
    [""],
    [],
  ]
  for (const segments of refused) {
    assert.equal(resolvePackFile("P1", segments), null, JSON.stringify(segments))
  }
})

test("a file of a pack with a bad id is refused", () => {
  assert.equal(resolvePackFile("../x", ["SKROT.html"]), null)
  assert.equal(resolvePackFile("", ["SKROT.html"]), null)
  assert.equal(resolvePackFile(null, ["SKROT.html"]), null)
})

test("content types follow the extension", () => {
  assert.equal(contentTypeFor("a/SKROT.html"), "text/html; charset=utf-8")
  assert.equal(contentTypeFor("a/x.PNG"), "image/png")
  assert.equal(contentTypeFor("meta.json"), "application/json; charset=utf-8")
  assert.equal(contentTypeFor("a.bin"), "application/octet-stream")
})
