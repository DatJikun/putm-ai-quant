import assert from "node:assert/strict"
import fs from "node:fs"
import path from "node:path"
import { test } from "node:test"
import { adaptAeropack } from "../src/lib/pack-adapter"
import { parseGeometryYaml, parseVehicleYaml } from "../src/lib/geometry-yaml"

// What ingest/pack.py writes with yaml.safe_dump when the cards come from the STEP file:
// block style, list items at column 0, single-quoted text, real booleans and nulls.
const BLOCK_STYLE = `vehicle:
  name: PM09
  halfModel: true
  rideHeightFrontMm: TBD
  wheelbaseMm: 1530
  frontalAreaM2: 0.5
devices:
- id: fw-main
  group: front-wing
  chordMm: 347.23
  profile: null
  le:
    xMm: -885.95
    zMm: 82.92
  te:
    xMm: -538.88
    zMm: 72.24
  notes: 'Przekrój Y=-315 mm: bez # kłopotu'
  measured: true
- id: rw-main
  group: rear-wing
  profile: TBD
  le:
    xMm: 1400
    zMm: 700
`

test("block-style cards keep nested LE/TE and quoted text intact", () => {
  const [fw, rw] = parseGeometryYaml(BLOCK_STYLE)
  assert.equal(fw.id, "fw-main")
  assert.deepEqual(fw.le, { xMm: -885.95, zMm: 82.92 })
  assert.deepEqual(fw.te, { xMm: -538.88, zMm: 72.24 })
  assert.equal(fw.notes, "Przekrój Y=-315 mm: bez # kłopotu")
  assert.equal((fw as Record<string, unknown>).measured, true)
  assert.equal(fw.profile, null)
  assert.equal(fw.chordMm, 347.23)
  assert.equal(rw.profile, null, "TBD is a gap, not a profile name")
  assert.deepEqual(rw.le, { xMm: 1400, zMm: 700 })
  assert.equal(rw.te, undefined)
})

test("vehicle block turns TBD into null and keeps numbers", () => {
  const vehicle = parseVehicleYaml(BLOCK_STYLE)
  assert.equal(vehicle.name, "PM09")
  assert.equal(vehicle.rideHeightFrontMm, null)
  assert.equal(vehicle.wheelbaseMm, 1530)
  assert.equal(vehicle.halfModel, true)
})

test("empty, missing and broken YAML give empty results, not a crash", () => {
  assert.deepEqual(parseGeometryYaml(undefined), [])
  assert.deepEqual(parseGeometryYaml(""), [])
  assert.deepEqual(parseGeometryYaml("devices: [unclosed"), [])
  assert.deepEqual(parseGeometryYaml("devices:\n  - group: no-id\n"), [])
  assert.deepEqual(parseVehicleYaml("vehicle: [unclosed"), {})
})

test("the team template parses to as many cards as it declares", () => {
  const text = fs.readFileSync(path.join(__dirname, "..", "templates", "geometry.yaml"), "utf-8")
  const declared = text.split(/\r?\n/).filter((line) => /^\s*-\s+id:/.test(line)).length
  const devices = parseGeometryYaml(text)
  assert.ok(declared > 0)
  assert.equal(devices.length, declared)
  const main = devices.find((device) => device.id === "fw-main")
  assert.equal(typeof main?.le?.xMm, "number")
  assert.equal(typeof main?.te?.zMm, "number")
})

test("adapter shows LE/TE from a STEP-derived geometry.yaml", () => {
  const adapted = adaptAeropack(
    {
      schema: "aeropack/v1",
      identity: { caseId: "c", vehicle: "X", halfModel: true, yawDeg: 0 },
      geometry: { status: "1 karta", deviceCount: 2 },
      warnings: [],
      notesForAgent: [],
    },
    [],
    BLOCK_STYLE,
  )
  assert.equal(adapted.devices.length, 2)
  assert.deepEqual(adapted.devices[0].le, { xMm: -885.95, zMm: 82.92 })
  assert.deepEqual(adapted.devices[0].te, { xMm: -538.88, zMm: 72.24 })
})
