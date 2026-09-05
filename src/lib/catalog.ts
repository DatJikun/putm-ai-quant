import type { Axis, FieldId, PostImage, RegionId } from "./types"

export const FIELD_LABEL: Record<FieldId, string> = {
  cp: "Cp",
  cpt: "Cp total",
  vel: "|V|",
  vort: "vorticity",
  tke: "TKE",
  helicity: "helicity",
  yplus: "y+",
  u: "Vx",
  pt: "p total",
}

export const AXIS_LABEL: Record<Axis, string> = {
  full: "cały bolid",
  x: "oś X (płaszczyzny YZ)",
  y: "oś Y (płaszczyzny XZ)",
  z: "oś Z (płaszczyzny XY)",
}

export const REGION_LABEL: Record<RegionId, string> = {
  "full-car": "cały bolid",
  nose: "nos",
  "front-wing": "przednie skrzydło",
  "front-axle": "oś przednia / koła",
  "floor-inlet": "wlot podłogi",
  cockpit: "kokpit / hoop",
  "rear-axle": "oś tylna",
  diffuser: "dyfuzor",
  "rear-wing": "tylne skrzydło",
  "near-wake": "bliski ślad",
  "far-wake": "daleki ślad",
  symmetry: "płaszczyzna symetrii",
  "inner-wheel": "wewnętrzna strona koła",
  "outer-wheel": "zewnętrzna strona koła",
  ground: "przy ziemi",
  underfloor: "podłoga",
  sidepod: "sidepod",
  "wing-height": "wysokość skrzydeł",
  "roll-hoop": "roll hoop",
}

const SLICE_FIELDS: FieldId[] = [
  "cp",
  "cpt",
  "vel",
  "vort",
  "tke",
  "helicity",
  "yplus",
  "u",
  "pt",
]

const FULL_CAMERAS = [
  "iso-front-left",
  "iso-front-right",
  "iso-rear-left",
  "iso-rear-right",
  "front",
  "rear",
  "side-left",
  "side-right",
  "top",
  "bottom",
  "three-quarter-fw",
  "three-quarter-rw",
] as const

const FULL_FIELDS: FieldId[] = ["cp", "cpt", "vel", "vort", "tke", "yplus", "pt"]

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t
}

function regionFromX(x: number): RegionId {
  if (x < 0.05) return "nose"
  if (x < 0.55) return "front-wing"
  if (x < 0.85) return "front-axle"
  if (x < 1.25) return "floor-inlet"
  if (x < 1.85) return "cockpit"
  if (x < 2.15) return "rear-axle"
  if (x < 2.45) return "diffuser"
  if (x < 2.85) return "rear-wing"
  if (x < 3.15) return "near-wake"
  return "far-wake"
}

function regionFromY(y: number): RegionId {
  const ay = Math.abs(y)
  if (ay < 0.08) return "symmetry"
  if (ay < 0.52) return "inner-wheel"
  return "outer-wheel"
}

function regionFromZ(z: number): RegionId {
  if (z < 0.04) return "ground"
  if (z < 0.16) return "underfloor"
  if (z < 0.38) return "sidepod"
  if (z < 0.72) return "wing-height"
  return "roll-hoop"
}

function pad(n: number, w = 3) {
  return String(n).padStart(w, "0")
}

let cached: PostImage[] | null = null

export function buildImageCatalog(): PostImage[] {
  if (cached) return cached
  const images: PostImage[] = []

  // 60 X × 9 fields = 540
  for (let i = 0; i < 60; i++) {
    const x = lerp(-0.35, 3.45, i / 59)
    const region = regionFromX(x)
    for (const field of SLICE_FIELDS) {
      const idx = i + 1
      images.push({
        id: `x-${field}-${pad(idx)}`,
        filename: `x/x_${pad(idx)}_${field}_${x.toFixed(3)}m.png`,
        axis: "x",
        field,
        stationM: Number(x.toFixed(3)),
        camera: "yz-slice",
        zoom: "full",
        region,
        hero: false,
      })
    }
  }

  // 40 Y × 9 = 360
  for (let i = 0; i < 40; i++) {
    const y = lerp(-0.75, 0.75, i / 39)
    const region = regionFromY(y)
    for (const field of SLICE_FIELDS) {
      const idx = i + 1
      images.push({
        id: `y-${field}-${pad(idx)}`,
        filename: `y/y_${pad(idx)}_${field}_${y.toFixed(3)}m.png`,
        axis: "y",
        field,
        stationM: Number(y.toFixed(3)),
        camera: "xz-slice",
        zoom: "full",
        region,
        hero: false,
      })
    }
  }

  // 48 Z × 9 = 432
  for (let i = 0; i < 48; i++) {
    const z = lerp(0.005, 1.15, i / 47)
    const region = regionFromZ(z)
    for (const field of SLICE_FIELDS) {
      const idx = i + 1
      images.push({
        id: `z-${field}-${pad(idx)}`,
        filename: `z/z_${pad(idx)}_${field}_${z.toFixed(3)}m.png`,
        axis: "z",
        field,
        stationM: Number(z.toFixed(3)),
        camera: "xy-slice",
        zoom: "full",
        region,
        hero: false,
      })
    }
  }

  // 12 cameras × 7 fields × 2 zoom = 168  → 540+360+432+168 = 1500
  for (const camera of FULL_CAMERAS) {
    for (const field of FULL_FIELDS) {
      for (const zoom of ["full", "detail"] as const) {
        images.push({
          id: `full-${camera}-${field}-${zoom}`,
          filename: `full/${camera}_${field}_${zoom}.png`,
          axis: "full",
          field,
          stationM: null,
          camera,
          zoom,
          region: "full-car",
          hero: false,
        })
      }
    }
  }

  markHeroes(images)
  if (images.length !== 1500) {
    throw new Error(`Katalog ma mieć 1500 klatek, jest ${images.length}`)
  }
  cached = images
  return images
}

const HERO_X = [0.28, 0.7, 1.05, 1.55, 2.0, 2.3, 2.65, 3.05]

function nearest(
  images: PostImage[],
  pred: (img: PostImage) => boolean,
): PostImage | undefined {
  return images.find(pred)
}

function closestStation(
  images: PostImage[],
  axis: Axis,
  field: FieldId,
  target: number,
) {
  const pool = images.filter((i) => i.axis === axis && i.field === field)
  return pool.reduce((best, img) => {
    if (img.stationM == null) return best
    if (!best || best.stationM == null) return img
    return Math.abs(img.stationM - target) < Math.abs(best.stationM - target)
      ? img
      : best
  }, undefined as PostImage | undefined)
}

function markHeroes(images: PostImage[]) {
  const heroes: Array<{ img?: PostImage; reason: string }> = [
    {
      img: nearest(
        images,
        (i) =>
          i.axis === "full" &&
          i.camera === "iso-front-left" &&
          i.field === "cp" &&
          i.zoom === "full",
      ),
      reason: "Mapa Cp całego bolidu — skąd pochodzi downforce i drag.",
    },
    {
      img: nearest(
        images,
        (i) =>
          i.axis === "full" &&
          i.camera === "bottom" &&
          i.field === "cp" &&
          i.zoom === "full",
      ),
      reason: "Spód: ssanie podłogi i dyfuzora.",
    },
    {
      img: nearest(
        images,
        (i) =>
          i.axis === "full" &&
          i.camera === "iso-rear-left" &&
          i.field === "vel" &&
          i.zoom === "full",
      ),
      reason: "Ślad za autem — jakość powietrza na tylne skrzydło.",
    },
    {
      img: nearest(
        images,
        (i) =>
          i.axis === "full" &&
          i.camera === "top" &&
          i.field === "yplus" &&
          i.zoom === "full",
      ),
      reason: "Kontrola y+ na skrzydłach i nadwoziu.",
    },
    {
      img: closestStation(images, "y", "cpt", 0),
      reason: "Płaszczyzna symetrii, Cp total — struktury wzdłuż auta.",
    },
    {
      img: closestStation(images, "y", "vel", 0),
      reason: "Płaszczyzna symetrii, prędkość — separacja i przyspieszenie pod spodem.",
    },
    {
      img: closestStation(images, "z", "cpt", 0.12),
      reason: "Przekrój podłogi — czy koła zatruwają dyfuzor.",
    },
    {
      img: closestStation(images, "z", "vel", 0.55),
      reason: "Wysokość głównych płatów skrzydeł.",
    },
    {
      img: closestStation(images, "x", "vort", 0.7),
      reason: "Wir za przednim kołem.",
    },
  ]

  for (const x of HERO_X) {
    heroes.push({
      img: closestStation(images, "x", "cpt", x),
      reason: `Stacja X=${x.toFixed(2)} m, Cp total — rozwój śladu.`,
    })
  }

  const seen = new Set<string>()
  for (const { img, reason } of heroes) {
    if (!img || seen.has(img.id)) continue
    seen.add(img.id)
    img.hero = true
    img.reason = reason
  }
}

export function catalogStats(images: PostImage[]) {
  const byAxis: Record<Axis, number> = { full: 0, x: 0, y: 0, z: 0 }
  const byField: Partial<Record<FieldId, number>> = {}
  for (const img of images) {
    byAxis[img.axis] += 1
    byField[img.field] = (byField[img.field] ?? 0) + 1
  }
  return {
    total: images.length,
    byAxis,
    byField,
    heroCount: images.filter((i) => i.hero).length,
  }
}
