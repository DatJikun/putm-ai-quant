/**
 * Kontrakt pliku zapisywanego przez `ingest/pack.py`.
 * Osobny kształt `AgentPack` w `types.ts` jest widokiem dema FS-26, nie tym plikiem.
 */
export const ingestAeropackSchema = {
  $id: "aeropack/v1",
  type: "object",
  required: ["schema", "warnings", "identity", "kpis", "notesForAgent"],
  properties: {
    schema: { const: "aeropack/v1" },
    warnings: { type: "array", items: { type: "string" } },
    identity: {
      type: "object",
      required: ["caseId", "vehicle", "halfModel", "yawDeg"],
    },
    monitors: {
      type: "object",
      properties: {
        iterations: { type: ["integer", "null"] },
        residuals: { type: "object" },
        yPlus: { type: "object" },
      },
    },
    kpis: {
      type: "object",
      properties: {
        Cd: { type: ["number", "null"] },
        Cl: { type: ["number", "null"] },
        references: { type: "object" },
      },
    },
    geometry: {
      type: "object",
      required: ["status", "deviceCount"],
    },
    images: {
      type: "object",
      properties: {
        total: { type: "integer" },
        hero: { type: "array" },
      },
    },
  },
} as const
