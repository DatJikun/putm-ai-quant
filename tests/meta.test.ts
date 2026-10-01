import assert from "node:assert/strict"
import { test } from "node:test"
import {
  frameImageUrl,
  megabytes,
  nearestPlane,
  packFileUrl,
  parseGallery,
  summarizeMeta,
  type Gallery,
} from "../src/lib/meta"

const META = {
  schemat: "aeropack-meta/v1",
  caseId: "C1",
  werdykt: { label: "Nie ufać wynikom bez poprawki" },
  wnioski: [
    { id: "a", waga: "wysoka", tekst: "Siły się zmieniają", dowod: "raport.checks[id=a]" },
    { id: "b", waga: "dziwna", tekst: "pominięte", dowod: "x" },
    { id: "c", waga: "info", tekst: "Docisk robi podłoga", dowod: "raport.walls.groups" },
    { id: "d", waga: "niska" },
  ],
  wiarygodnosc: {
    score: 70,
    coverage: 91,
    label: "Niska wiarygodność",
    byCategory: { "Siatka i ściana": 78, "Zgodność z pomiarem": null },
    checks: [
      { id: "yplus", title: "y+", status: "ok", weight: 10, value: "0.5", detail: "dobrze", sources: ["menter"] },
      { id: "zly", title: "zły status", status: "nieznany", weight: 1, value: "", detail: "", sources: [] },
    ],
    unknown: ["Zgodność z pomiarem"],
  },
  zrodla: { sily_na_czesci: { zrodlo: ".cas.h5 + .dat.h5", metoda: "ciśnienie razy pole", dokladnosc: "dokładne" } },
  oryginaly: { bajtyRazem: 22.2e9 },
  mapy: { powierzchnia: { "1cm": { bajty: 790_000 }, "3mm": { bajty: 4_450_000 } }, przekroje: { bajty: 9_430_000 } },
}

test("a meta summary keeps the findings it understands, in order", () => {
  const s = summarizeMeta(META)
  assert.ok(s)
  assert.equal(s.caseId, "C1")
  assert.equal(s.verdict, "Nie ufać wynikom bez poprawki")
  assert.deepEqual(
    s.findings.map((f) => [f.id, f.weight]),
    [
      ["a", "wysoka"],
      ["c", "info"],
    ],
  )
  assert.equal(s.findings[0].evidence, "raport.checks[id=a]")
})

test("credibility keeps valid checks and null group scores", () => {
  const s = summarizeMeta(META)
  assert.ok(s?.credibility)
  assert.equal(s.credibility.score, 70)
  assert.equal(s.credibility.coverage, 91)
  assert.deepEqual(s.credibility.checks.map((c) => c.id), ["yplus"])
  assert.deepEqual(s.credibility.checks[0].sources, ["menter"])
  assert.equal(s.credibility.byCategory["Zgodność z pomiarem"], null)
  assert.deepEqual(s.credibility.unknown, ["Zgodność z pomiarem"])
})

test("sizes: the original case files and the maps that replace them", () => {
  const s = summarizeMeta(META)
  assert.equal(s?.originalsBytes, 22.2e9)
  assert.equal(s?.metaBytes, 790_000 + 4_450_000 + 9_430_000)
  assert.deepEqual(s?.provenance, [
    { name: "sily_na_czesci", source: ".cas.h5 + .dat.h5", method: "ciśnienie razy pole", accuracy: "dokładne" },
  ])
})

test("something that is not a meta file is refused", () => {
  assert.equal(summarizeMeta(null), null)
  assert.equal(summarizeMeta({}), null)
  assert.equal(summarizeMeta({ schemat: "aeropack/v1" }), null)
  assert.equal(summarizeMeta("tekst"), null)
})

test("a meta file without credibility or maps still summarizes", () => {
  const s = summarizeMeta({ schemat: "aeropack-meta/v1" })
  assert.ok(s)
  assert.equal(s.credibility, null)
  assert.equal(s.metaBytes, null)
  assert.deepEqual(s.findings, [])
})

const GALLERY: Gallery = {
  planes: { x: [-1.1, -1.0758, 0.0, 1.8], y: [-0.01, -0.5], z: [0.0, 0.3] },
  fields: ["cp", "cpt", "vel"],
  surface: ["cp_z-boku.png", "cp_z-gory.png", "cp_z-przodu.png", "yplus_z-boku.png"],
}

test("the gallery is read from obrazy/index.json and refuses an empty one", () => {
  const g = parseGallery({ positions: { x: [0, 0.1], y: [], z: ["a", 1] }, fields: ["cp"], surface: ["cp_z-boku.png"] })
  assert.deepEqual(g, { planes: { x: [0, 0.1], z: [1] }, fields: ["cp"], surface: ["cp_z-boku.png"] })
  assert.equal(parseGallery({}), null)
  assert.equal(parseGallery({ positions: { x: [] } }), null)
})

test("the nearest plane position is picked", () => {
  assert.equal(nearestPlane([0, 1, 2], 1.4), 1)
  assert.equal(nearestPlane([0, 1, 2], 1.6), 2)
  assert.equal(nearestPlane([-1.1, -1.0758], -1.09), -1.1)
  assert.equal(nearestPlane([], 1), null)
})

test("a CFD-Post frame is matched to our own picture of the nearest plane", () => {
  assert.equal(
    frameImageUrl("P 1", GALLERY, "x", "cp", 1.7),
    "/api/packs/files/P%201/obrazy/przekroje/x/cp/x_1.800.png",
  )
  assert.equal(
    frameImageUrl("P1", GALLERY, "x", "pt", -1.09),
    "/api/packs/files/P1/obrazy/przekroje/x/cpt/x_-1.100.png",
  )
  assert.equal(frameImageUrl("P1", GALLERY, "z", "vel", 0.28), "/api/packs/files/P1/obrazy/przekroje/z/vel/z_0.300.png")
})

test("frames without a picture of ours stay without one", () => {
  assert.equal(frameImageUrl("P1", GALLERY, "x", "vort", 1.0), null)
  assert.equal(frameImageUrl("P1", GALLERY, "x", "cp", null), null)
  assert.equal(frameImageUrl("P1", null, "x", "cp", 1.0), null)
  assert.equal(frameImageUrl("P1", { ...GALLERY, planes: {} }, "x", "cp", 1.0), null)
  assert.equal(frameImageUrl("P1", { ...GALLERY, fields: ["cp"] }, "x", "cpt", 1.0), null)
})

test("full-car frames use the wall view that matches the camera", () => {
  assert.equal(frameImageUrl("P1", GALLERY, "full", "cp", null, "z góry"), "/api/packs/files/P1/obrazy/powierzchnia/cp_z-gory.png")
  assert.equal(frameImageUrl("P1", GALLERY, "full", "cp", null, "front"), "/api/packs/files/P1/obrazy/powierzchnia/cp_z-przodu.png")
  assert.equal(frameImageUrl("P1", GALLERY, "full", "yplus", null, "Cp"), "/api/packs/files/P1/obrazy/powierzchnia/yplus_z-boku.png")
  assert.equal(frameImageUrl("P1", GALLERY, "full", "vel", null), null)
})

test("file urls escape every segment", () => {
  assert.equal(packFileUrl("A B", "obrazy/galeria.html"), "/api/packs/files/A%20B/obrazy/galeria.html")
})

test("sizes are shown in plain units", () => {
  assert.equal(megabytes(null), "brak")
  assert.equal(megabytes(22.2e9), "22.2 GB")
  assert.equal(megabytes(14_970_000), "15 MB")
  assert.equal(megabytes(790_000), "0.8 MB")
})
