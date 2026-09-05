/** JSON Schema-shaped contract for AeroPack v1 (documentation + runtime type). */
export const aeropackSchema = {
  $id: "aeropack/v1",
  type: "object",
  required: [
    "schema",
    "case",
    "cad",
    "kpis",
    "imageCatalog",
    "heroFrames",
    "notesForAgent",
  ],
  properties: {
    schema: { const: "aeropack/v1" },
    case: {
      type: "object",
      required: ["casFile", "datFile", "turbulence", "residuals", "yPlusWings"],
    },
    cad: {
      type: "object",
      required: [
        "wheelbaseMm",
        "frontalAreaM2",
        "rideHeightFrontMm",
        "components",
      ],
    },
    kpis: {
      type: "object",
      required: ["Cd", "Cl", "LOverD", "frontBalancePct", "components"],
    },
    imageCatalog: {
      type: "object",
      required: ["total", "byAxis", "heroCount"],
    },
    heroFrames: { type: "array", maxItems: 32 },
  },
} as const
