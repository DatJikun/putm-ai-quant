import { catalogStats } from "./catalog"
import type {
  AeroKpis,
  AgentPack,
  CadModel,
  FluentCase,
  PostImage,
} from "./types"

export function buildAgentPack(
  fluent: FluentCase,
  cad: CadModel,
  kpis: AeroKpis,
  images: PostImage[],
): AgentPack {
  const stats = catalogStats(images)
  const heroes = images.filter((i) => i.hero)

  return {
    schema: "aeropack/v1",
    generatedAt: "2026-09-05T11:00:00Z",
    case: fluent,
    cad,
    kpis,
    imageCatalog: stats,
    heroFrames: heroes.map((h) => ({
      filename: h.filename,
      axis: h.axis,
      field: h.field,
      stationM: h.stationM,
      region: h.region,
      why: h.reason ?? "klatka kluczowa",
    })),
    notesForAgent: [
      "Jesteś recenzentem aero Formula Student, nie generatorem ładnych zdań.",
      "Liczby z .cas/.dat mają pierwszeństwo przed interpretacją pikseli.",
      "Obrazek bez skali, jednostek i stacji jest anegdotą — oznacz jako słabe evidence.",
      "Nie wnioskuj stallu z jednej klatki Cp; szukaj spójności X (ślad) + Z (podłoga) + siły komponentu.",
      "Porównuj do zakresów FS, nie do F1.",
      "Jeśli y+ i model turbulencji się kłócą, obniż pewność sił na skrzydłach.",
      "CAD służy do kotwiczenia stacji (oś, ride height, hoop), nie do oceniania stylistyki.",
    ],
  }
}

export function packAsPrompt(pack: AgentPack) {
  return [
    "# AeroPack v1 — recenzja case CFD Formula Student",
    "",
    pack.notesForAgent.map((n) => `- ${n}`).join("\n"),
    "",
    "## Case",
    "```json",
    JSON.stringify(
      {
        case: pack.case,
        cad: pack.cad,
        kpis: pack.kpis,
        imageCatalog: pack.imageCatalog,
        heroFrames: pack.heroFrames,
      },
      null,
      2,
    ),
    "```",
    "",
    "Dołączone są wyłącznie ramki oznaczone hero (obrazy). Reszta katalogu to indeks — możesz poprosić o konkretną stację.",
  ].join("\n")
}
