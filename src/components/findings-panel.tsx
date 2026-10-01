import {
  STATUS_LABEL,
  WEIGHT_LABEL,
  megabytes,
  packFileUrl,
  type CheckStatus,
  type FindingWeight,
  type MetaSummary,
} from "@/lib/meta"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

const WEIGHT_CLASS: Record<FindingWeight, string> = {
  wysoka: "border-red-500/50 bg-red-500/10 text-red-200",
  srednia: "border-amber-400/40 bg-amber-400/10 text-amber-200",
  niska: "border-white/20 bg-white/5 text-muted-foreground",
  info: "border-[#5ee0c0]/40 bg-[#5ee0c0]/10 text-[#9af0dc]",
}

const STATUS_CLASS: Record<CheckStatus, string> = {
  ok: "text-[#5ee0c0]",
  uwaga: "text-amber-300",
  zle: "text-red-300",
  brak: "text-muted-foreground",
}

const LINKS: readonly [string, string][] = [
  ["SKROT.html", "Dokument skrótowy"],
  ["PELNY.html", "Dokument pełny"],
  ["obrazy/galeria.html", "Galeria przekrojów"],
]

function Bar({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>{label}</span>
        <span className="font-mono text-foreground">{value == null ? "nie sprawdzono" : value}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
        <div
          className={`h-full rounded-full ${value == null ? "bg-white/20" : "bg-[#5ee0c0]"}`}
          style={{ width: `${value ?? 0}%` }}
        />
      </div>
    </div>
  )
}

/** What the meta pack concludes by itself: findings, how far to trust the run, where each number came from. */
export function FindingsPanel({ packId, meta }: { packId: string; meta: MetaSummary }) {
  const cred = meta.credibility
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        {meta.verdict && <Badge className="h-7 rounded-md bg-[#f4c14d] px-3 text-[#1a1406]">{meta.verdict}</Badge>}
        <span className="text-sm text-muted-foreground">
          {meta.originalsBytes != null && meta.metaBytes != null
            ? `Pliki Fluenta: ${megabytes(meta.originalsBytes)} → metaplik z mapami: ${megabytes(meta.metaBytes)}`
            : "Wnioski wyciągnięte z plików symulacji"}
        </span>
        {LINKS.map(([file, label]) => (
          <a
            key={file}
            className="text-xs text-[#5ee0c0] underline underline-offset-2"
            href={packFileUrl(packId, file)}
            target="_blank"
            rel="noreferrer"
          >
            {label}
          </a>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Wnioski ({meta.findings.length})</CardTitle>
          <CardDescription>Od najważniejszych. Każdy ma wskazany dowód w danych.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {meta.findings.length === 0 && <p className="text-sm text-muted-foreground">Metaplik nie zawiera wniosków.</p>}
          {meta.findings.map((f) => (
            <div key={f.id} className="flex flex-wrap items-start gap-2 text-sm">
              <span className={`rounded-md border px-2 py-0.5 text-[11px] uppercase ${WEIGHT_CLASS[f.weight]}`}>
                {WEIGHT_LABEL[f.weight]}
              </span>
              <div className="min-w-0 flex-1">
                <p className="leading-relaxed">{f.text}</p>
                {f.evidence && <p className="font-mono text-[11px] text-muted-foreground">dowód: {f.evidence}</p>}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {cred && (
        <Card>
          <CardHeader>
            <CardTitle>
              Wiarygodność: {cred.score == null ? "brak oceny" : `${cred.score}/100`}
              {cred.coverage != null ? ` (sprawdzono ${cred.coverage}% kryteriów)` : ""}
            </CardTitle>
            <CardDescription>
              {cred.label}. Zgodność z rzeczywistością da się ocenić tylko z pomiarów (plik pomiary.json).
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {Object.entries(cred.byCategory).map(([name, value]) => (
                <Bar key={name} label={name} value={value} />
              ))}
            </div>
            <ul className="space-y-2">
              {cred.checks.map((c) => (
                <li key={c.id || c.title} className="text-sm">
                  <span className={`font-mono text-[11px] ${STATUS_CLASS[c.status]}`}>[{STATUS_LABEL[c.status]}]</span>{" "}
                  <span className="font-medium">{c.title}</span>
                  {c.value && <span className="text-muted-foreground"> — {c.value}</span>}
                  {c.detail && <p className="text-xs leading-relaxed text-muted-foreground">{c.detail}</p>}
                  {c.sources.length > 0 && (
                    <p className="font-mono text-[10px] text-muted-foreground/80">źródła: {c.sources.join(", ")}</p>
                  )}
                </li>
              ))}
            </ul>
            {cred.unknown.length > 0 && (
              <p className="text-xs text-amber-200/90">Nie dało się sprawdzić: {cred.unknown.join("; ")}.</p>
            )}
          </CardContent>
        </Card>
      )}

      {meta.provenance.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Skąd jest każda liczba</CardTitle>
            <CardDescription>Plik źródłowy, metoda i dokładność. Nic nie jest zgadywane po cichu.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1.5 text-xs">
              {meta.provenance.map((p) => (
                <li key={p.name}>
                  <span className="font-mono text-[#5ee0c0]">{p.name}</span>
                  <span className="text-muted-foreground">
                    {" "}
                    · {p.source} · {p.method} · {p.accuracy}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
