"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import {
  AXIS_LABEL,
  FIELD_LABEL,
  REGION_LABEL,
  catalogStats,
} from "@/lib/catalog"
import {
  cad as demoCad,
  fluentCase as demoFluentCase,
  getDemoImages,
  kpis as demoKpis,
  reynolds as demoReynolds,
} from "@/lib/demo-case"
import { evaluateCase, VERDICT_LABEL } from "@/lib/agent"
import { buildAgentPack, packAsPrompt } from "@/lib/pack"
import { adaptAeropack, type AdaptedPack } from "@/lib/pack-adapter"
import type { Axis, FieldId, Severity } from "@/lib/types"
import { ContourPreview } from "@/components/contour-preview"
import { CarSchematic } from "@/components/car-schematic"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  AlertTriangle,
  Check,
  Code2,
  Copy,
  FileCheck2,
  FolderGit2,
  RefreshCw,
  Upload,
} from "lucide-react"

const PAGE = 25

const SEVERITY_CLASS: Record<Severity, string> = {
  info: "border-[#5ee0c0]/40 bg-[#5ee0c0]/10 text-[#9af0dc]",
  watch: "border-amber-400/40 bg-amber-400/10 text-amber-200",
  issue: "border-orange-500/40 bg-orange-500/10 text-orange-200",
  blocker: "border-red-500/50 bg-red-500/10 text-red-200",
}

type PackSummary = {
  id: string
  name: string
  vehicle: string
  generatedAt?: string
  cells?: number
  imagesTotal?: number
  heroCount?: number
  warningsCount?: number
  isLocal?: boolean
}

function fmtNum(value: number | null | undefined, digits = 2, suffix = "") {
  if (value == null || Number.isNaN(value)) return "brak"
  return `${value.toFixed(digits)}${suffix}`
}

function ScoreBar({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>{label}</span>
        <span className="font-mono text-foreground">{value == null ? "brak" : value}</span>
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

function buildDemoAdaptedPack(): AdaptedPack {
  const images = getDemoImages()
  const review = evaluateCase(demoFluentCase, demoKpis, demoCad, images)
  const pack = buildAgentPack(demoFluentCase, demoCad, demoKpis, images)
  const prompt = packAsPrompt(pack)

  return {
    id: "demo-fs26",
    name: "FS-26 (Syntetyczny Demo)",
    isLocal: false,
    warnings: [],
    notesForAgent: pack.notesForAgent,
    fluentCase: demoFluentCase,
    cad: demoCad,
    kpis: demoKpis,
    images,
    review,
    devices: [],
    reynolds: demoReynolds(),
    dataGaps: [],
    rawPack: pack,
    prompt,
  }
}

export function Workbench() {
  const [availablePacks, setAvailablePacks] = useState<PackSummary[]>([])
  const [selectedPackId, setSelectedPackId] = useState<string>("demo-fs26")
  const [packData, setPackData] = useState<AdaptedPack>(buildDemoAdaptedPack)
  const [isLoading, setIsLoading] = useState<boolean>(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [showRawJson, setShowRawJson] = useState(false)

  const [axis, setAxis] = useState<Axis | "all">("all")
  const [field, setField] = useState<FieldId | "all">("all")
  const [heroOnly, setHeroOnly] = useState(false)
  const [page, setPage] = useState(0)
  const [copied, setCopied] = useState(false)
  const [selectedHeroId, setSelectedHeroId] = useState<string>("")
  const [askText, setAskText] = useState<string>("")

  const fileInputRef = useRef<HTMLInputElement>(null)

  // Fetch pack list on mount
  const fetchPackList = async (preferPackId?: string) => {
    try {
      setIsLoading(true)
      setLoadError(null)
      const res = await fetch("/api/packs")
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      if (data.ok && Array.isArray(data.packs)) {
        setAvailablePacks(data.packs)
        // If we found local packs, pick preferred or first one
        if (data.packs.length > 0) {
          const target = preferPackId || data.packs[0].id
          await loadPack(target)
        }
      }
    } catch (err: any) {
      console.warn("Nie udało się pobrać listy packów z /api/packs:", err)
      // fallback stays on demo pack
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchPackList("BASELINEiter002")
  }, [])

  const loadPack = async (packId: string) => {
    if (packId === "demo-fs26") {
      setSelectedPackId("demo-fs26")
      setPackData(buildDemoAdaptedPack())
      setLoadError(null)
      return
    }

    try {
      setIsLoading(true)
      setLoadError(null)
      const res = await fetch(`/api/packs?id=${encodeURIComponent(packId)}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}: nie znaleziono packa`)
      const data = await res.json()
      if (!data.ok || !data.pack) {
        throw new Error(data.error || "Błąd formatu odpowiedzi z /api/packs")
      }

      const adapted = adaptAeropack(data.pack, data.images, data.geometryYaml)
      setSelectedPackId(packId)
      setPackData(adapted)
      setPage(0)
      if (adapted.images.length > 0) {
        const firstHero = adapted.images.find((i) => i.hero)
        if (firstHero) setSelectedHeroId(firstHero.id)
      }
    } catch (err: any) {
      setLoadError(err.message || "Błąd ładowania packa")
    } finally {
      setIsLoading(false)
    }
  }

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (event) => {
      try {
        const rawJson = JSON.parse(event.target?.result as string)
        const adapted = adaptAeropack(rawJson)
        setSelectedPackId("custom")
        setPackData(adapted)
        setLoadError(null)
        setPage(0)
        if (adapted.images.length > 0) {
          const firstHero = adapted.images.find((i) => i.hero)
          if (firstHero) setSelectedHeroId(firstHero.id)
        }
      } catch (err: any) {
        setLoadError("Niepoprawny plik JSON: " + err.message)
      }
    }
    reader.readAsText(file)
  }

  const {
    fluentCase,
    cad,
    kpis,
    images,
    review,
    prompt,
    warnings,
    devices,
    notesForAgent,
    dataGaps,
  } = packData
  const stats = useMemo(() => catalogStats(images), [images])
  const heroes = useMemo(() => images.filter((i) => i.hero), [images])

  useEffect(() => {
    if (heroes.length > 0 && !heroes.some((h) => h.id === selectedHeroId)) {
      setSelectedHeroId(heroes[0].id)
    }
  }, [heroes, selectedHeroId])

  const filtered = useMemo(() => {
    return images.filter((img) => {
      if (axis !== "all" && img.axis !== axis) return false
      if (field !== "all" && img.field !== field) return false
      if (heroOnly && !img.hero) return false
      return true
    })
  }, [images, axis, field, heroOnly])

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE))
  const slice = filtered.slice(page * PAGE, page * PAGE + PAGE)
  const selectedHero = heroes.find((h) => h.id === selectedHeroId) ?? heroes[0]

  async function copyPack() {
    await navigator.clipboard.writeText(prompt)
    setCopied(true)
    setTimeout(() => setCopied(false), 1600)
  }

  return (
    <div className="space-y-6">
      {/* Top Pack Selector Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-[#07090d] p-3.5 shadow-sm">
        <div className="flex flex-wrap items-center gap-2.5">
          <FolderGit2 className="size-4 text-[#5ee0c0]" />
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Aktywny pack:
          </span>
          <select
            className="h-9 rounded-md border border-white/15 bg-[#0e1218] px-3 text-sm font-medium text-foreground transition-colors hover:border-white/30 focus:border-[#5ee0c0] focus:outline-none"
            value={selectedPackId}
            onChange={(e) => loadPack(e.target.value)}
            disabled={isLoading}
          >
            {availablePacks.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} {p.isLocal ? "(Lokalny z packs/)" : ""}
              </option>
            ))}
            <option value="demo-fs26">Syntetyczny FS-26 (Demo)</option>
            {selectedPackId === "custom" && (
              <option value="custom">Wgrany plik JSON ({packData.id})</option>
            )}
          </select>

          {packData.isLocal ? (
            <Badge className="border border-[#1ec9b6]/40 bg-[#1ec9b6]/15 font-mono text-xs text-[#5ee0c0]">
              Lokalny case
            </Badge>
          ) : (
            <Badge variant="outline" className="border-white/20 font-mono text-xs text-muted-foreground">
              Demo case
            </Badge>
          )}

          <span className="hidden text-xs text-muted-foreground sm:inline">
            · {fmtNum(fluentCase.cellsM, 2)}M komórek · {fluentCase.iterations ?? "brak"} iter. · {stats.total} klatek
          </span>
        </div>

        <div className="flex items-center gap-2">
          <input
            type="file"
            ref={fileInputRef}
            accept=".json"
            className="hidden"
            onChange={handleFileUpload}
          />
          <Button
            variant="outline"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
            className="gap-1.5 text-xs"
          >
            <Upload className="size-3.5 text-muted-foreground" />
            Wczytaj JSON
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => fetchPackList(selectedPackId)}
            disabled={isLoading}
            title="Odśwież listę z folderu packs/"
          >
            <RefreshCw className={`size-3.5 text-muted-foreground ${isLoading ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </div>

      {loadError && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
          <p className="font-semibold">Błąd ładowania packa:</p>
          <p className="text-xs opacity-90">{loadError}</p>
        </div>
      )}

      {/* Tabs */}
      <Tabs defaultValue="zrodla" className="gap-5">
        <TabsList variant="line" className="w-full flex-wrap justify-start">
          <TabsTrigger value="zrodla">1. Źródła</TabsTrigger>
          <TabsTrigger value="katalog">2. Katalog ({stats.total})</TabsTrigger>
          <TabsTrigger value="kpi">3. Liczby + CAD</TabsTrigger>
          <TabsTrigger value="pack">4. Agent pack</TabsTrigger>
          <TabsTrigger value="ocena">5. Ocena</TabsTrigger>
        </TabsList>

        {/* Tab 1: Źródła */}
        <TabsContent value="zrodla" className="space-y-4">
          {warnings.length > 0 && (
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3.5 text-amber-200">
              <div className="flex items-center gap-2 font-medium">
                <AlertTriangle className="size-4 text-amber-400" />
                <span>Ostrzeżenia z inwentaryzacji i ingestu ({warnings.length}):</span>
              </div>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-amber-300/90">
                {warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="grid gap-3 md:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle>Fluent</CardTitle>
                <CardDescription>solver, siatka i przebieg obliczeń</CardDescription>
              </CardHeader>
              <CardContent className="space-y-1 font-mono text-xs">
                <p className="truncate font-medium text-[#5ee0c0]" title={fluentCase.casFile}>
                  {fluentCase.casFile}
                </p>
                <p className="truncate text-muted-foreground" title={fluentCase.datFile}>
                  {fluentCase.datFile}
                </p>
                <p className="pt-2 text-muted-foreground">{fluentCase.solver}</p>
                <p className="text-foreground">
                  {fmtNum(fluentCase.cellsM, 2)} mln komórek · {fluentCase.iterations ?? "brak"} iter.
                </p>
                <p className="text-muted-foreground">{fluentCase.wallTreatment}</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>CAD & Geometria</CardTitle>
                <CardDescription>kotwica stacji i intencja projektowa</CardDescription>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                <p className="truncate font-mono text-xs text-[#5ee0c0]" title={cad.name}>
                  {cad.name}
                </p>
                <p>
                  Rozstaw {fmtNum(cad.wheelbaseMm, 0)} mm · Aref = {fmtNum(cad.frontalAreaM2, 2)} m²
                </p>
                <p>
                  RH {fmtNum(cad.rideHeightFrontMm, 0)}/{fmtNum(cad.rideHeightRearMm, 0)} mm · rake{" "}
                  {fmtNum(cad.rakeDeg, 2)}°
                </p>
                <p className="text-xs text-muted-foreground">
                  {devices.length > 0
                    ? `${devices.length} kart urządzeń z geometry.yaml`
                    : `${cad.components.length} zdefiniowanych grup części`}
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Post-processing</CardTitle>
                <CardDescription>rejestr klatek z CFD-Post batch</CardDescription>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                <p>
                  <span className="font-mono text-lg font-semibold text-[#5ee0c0]">
                    {stats.total}
                  </span>{" "}
                  plików w indeksie
                </p>
                <p>
                  full {stats.byAxis.full} · X {stats.byAxis.x} · Y {stats.byAxis.y} · Z {stats.byAxis.z}
                </p>
                <p className="text-xs text-muted-foreground">
                  {stats.heroCount} hero klatek trafia do VLM, reszta to dopytywanie
                </p>
              </CardContent>
            </Card>
          </div>

          {dataGaps.length > 0 && (
            <div className="rounded-lg border border-orange-500/40 bg-orange-500/10 p-3.5 text-orange-100">
              <p className="font-medium">Pola, których nie uzupełniono ({dataGaps.length})</p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-orange-100/90">
                {dataGaps.map((gap) => (
                  <li key={gap}>{gap}</li>
                ))}
              </ul>
            </div>
          )}

          {notesForAgent.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-semibold">
                  Zasady kontraktu agenta (notesForAgent)
                </CardTitle>
                <CardDescription>
                  Twarde założenia inżynierskie przekazywane w każdym packu
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="list-disc space-y-1 pl-4 text-xs leading-relaxed text-muted-foreground">
                  {notesForAgent.map((note, idx) => (
                    <li key={idx}>{note}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Tab 2: Katalog */}
        <TabsContent value="katalog" className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <select
              className="h-8 rounded-md border border-white/15 bg-[#0e1218] px-2 text-sm"
              value={axis}
              onChange={(e) => {
                setAxis(e.target.value as Axis | "all")
                setPage(0)
              }}
            >
              <option value="all">wszystkie osie</option>
              {(["full", "x", "y", "z"] as Axis[]).map((a) => (
                <option key={a} value={a}>
                  {AXIS_LABEL[a]}
                </option>
              ))}
            </select>
            <select
              className="h-8 rounded-md border border-white/15 bg-[#0e1218] px-2 text-sm"
              value={field}
              onChange={(e) => {
                setField(e.target.value as FieldId | "all")
                setPage(0)
              }}
            >
              <option value="all">wszystkie pola</option>
              {(Object.keys(FIELD_LABEL) as FieldId[]).map((f) => (
                <option key={f} value={f}>
                  {FIELD_LABEL[f]}
                </option>
              ))}
            </select>
            <Button
              variant={heroOnly ? "default" : "outline"}
              onClick={() => {
                setHeroOnly((v) => !v)
                setPage(0)
              }}
            >
              {heroOnly ? "tylko hero" : "pokaż hero"}
            </Button>
            <span className="text-xs text-muted-foreground">
              {filtered.length} klatek · strona {page + 1}/{pageCount}
            </span>
          </div>

          <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
            <Card>
              <CardHeader>
                <CardTitle>Indeks klatek</CardTitle>
                <CardDescription>
                  Agent otrzymuje indeks. PNG są renderowane lub dopytywane na żądanie.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>plik</TableHead>
                        <TableHead>oś</TableHead>
                        <TableHead>pole</TableHead>
                        <TableHead>stacja</TableHead>
                        <TableHead>region</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {slice.map((img) => (
                        <TableRow
                          key={img.id}
                          className={img.hero ? "bg-[#5ee0c0]/8" : undefined}
                        >
                          <TableCell className="max-w-[200px] truncate font-mono text-[11px]" title={img.filename}>
                            {img.hero ? "★ " : ""}
                            {img.filename}
                          </TableCell>
                          <TableCell>{img.axis}</TableCell>
                          <TableCell>{FIELD_LABEL[img.field] || img.field}</TableCell>
                          <TableCell className="font-mono">
                            {img.stationM == null ? "—" : `${img.stationM.toFixed(2)} m`}
                          </TableCell>
                          <TableCell>{REGION_LABEL[img.region] || img.region}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
                <div className="mt-3 flex gap-2">
                  <Button
                    variant="outline"
                    disabled={page === 0}
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                  >
                    wstecz
                  </Button>
                  <Button
                    variant="outline"
                    disabled={page >= pageCount - 1}
                    onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
                  >
                    dalej
                  </Button>
                </div>
              </CardContent>
            </Card>

            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Hero klatki ({heroes.length}) — obrazy wchodzące w skład pierwszego zapytania do agenta.
              </p>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {heroes.slice(0, 18).map((h) => (
                  <button
                    key={h.id}
                    type="button"
                    onClick={() => setSelectedHeroId(h.id)}
                    className={`overflow-hidden rounded-lg ring-1 transition-all ${
                      selectedHero?.id === h.id
                        ? "ring-2 ring-[#5ee0c0]"
                        : "ring-white/10 hover:ring-white/30"
                    }`}
                  >
                    <ContourPreview
                      id={h.id}
                      axis={h.axis}
                      field={h.field}
                      stationM={h.stationM}
                    />
                  </button>
                ))}
              </div>
              {selectedHero && (
                <div className="rounded-lg border border-white/10 bg-[#07090d] p-3 text-sm">
                  <p className="font-mono text-xs text-muted-foreground truncate" title={selectedHero.filename}>
                    {selectedHero.filename}
                  </p>
                  <p className="mt-1 leading-relaxed">
                    <span className="font-medium text-[#5ee0c0]">
                      {REGION_LABEL[selectedHero.region] || selectedHero.region}
                    </span>
                    {" — "}
                    {selectedHero.reason || "Kluczowa stacja pomiarowa do wglądu"}
                  </p>
                </div>
              )}
            </div>
          </div>
        </TabsContent>

        {/* Tab 3: Liczby + CAD */}
        <TabsContent value="kpi" className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ["Cl (downforce)", kpis.Cl == null ? "brak" : Math.abs(kpis.Cl).toFixed(2)],
              ["Cd (drag)", fmtNum(kpis.Cd, 2)],
              ["L/D (efektywność)", fmtNum(kpis.LOverD, 2)],
              ["balans przód", kpis.frontBalancePct == null ? "brak" : `${kpis.frontBalancePct} %`],
            ].map(([label, value]) => (
              <Card key={label} size="sm">
                <CardHeader>
                  <CardDescription>{label}</CardDescription>
                  <CardTitle className="font-mono text-2xl">{value}</CardTitle>
                </CardHeader>
              </Card>
            ))}
          </div>

          <p className="text-sm text-muted-foreground">
            {fmtNum(kpis.downforceN, 0)} N downforce / {fmtNum(kpis.dragN, 0)} N drag przy{" "}
            {fluentCase.speedMs ?? "brak"} m/s (konwencja {packData.rawPack?.kpis?.forceConvention || "half-model"}) · Re ≈{" "}
            {packData.reynolds == null ? "brak" : `${(packData.reynolds / 1e6).toFixed(2)}×10`}
            {packData.reynolds != null && <sup>6</sup>}
          </p>

          <Card>
            <CardHeader>
              <CardTitle>Siły według stref i komponentów</CardTitle>
              <CardDescription>
                Rozbicie aerodynamiczne ze ścian auta (z wyłączeniem ścian tunelu)
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>komponent</TableHead>
                      <TableHead>Cl (DF)</TableHead>
                      <TableHead>Cd</TableHead>
                      <TableHead>% downforce</TableHead>
                      <TableHead>% drag</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {kpis.components.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={5} className="text-muted-foreground">
                          Brak podziału sił po strefach. To nie jest zestaw z dema — pole zostaje puste.
                        </TableCell>
                      </TableRow>
                    ) : (
                      kpis.components.map((c) => (
                        <TableRow key={c.name}>
                          <TableCell className="font-medium">{c.name}</TableCell>
                          <TableCell className="font-mono">
                            {c.Cl == null ? "brak" : Math.abs(c.Cl).toFixed(2)}
                          </TableCell>
                          <TableCell className="font-mono">{fmtNum(c.Cd, 2)}</TableCell>
                          <TableCell className="font-mono">{fmtNum(c.shareDownforcePct, 1, "%")}</TableCell>
                          <TableCell className="font-mono">{fmtNum(c.shareDragPct, 1, "%")}</TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>

          {devices.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Karty geometrii urządzeń (geometry.yaml / STEP)</CardTitle>
                <CardDescription>
                  Parametryczne dane płatów i brył odniesienia ({devices.length} pozycji)
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>element (id)</TableHead>
                        <TableHead>rola</TableHead>
                        <TableHead>cięciwa [mm]</TableHead>
                        <TableHead>span [mm]</TableHead>
                        <TableHead>AoA [°]</TableHead>
                        <TableHead>LE [mm]</TableHead>
                        <TableHead>TE [mm]</TableHead>
                        <TableHead>uwagi</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {devices.map((d) => (
                        <TableRow key={d.id}>
                          <TableCell className="font-mono text-xs font-semibold text-[#5ee0c0]">
                            {d.id}
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {d.role || d.group || "—"}
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            {d.chordMm != null ? d.chordMm.toFixed(1) : "—"}
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            {d.spanMm != null ? d.spanMm : "—"}
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            {d.incidenceDeg != null ? `${d.incidenceDeg.toFixed(1)}°` : "—"}
                          </TableCell>
                          <TableCell className="font-mono text-[11px] text-muted-foreground">
                            {d.le ? `(${d.le.xMm.toFixed(0)}, ${d.le.zMm.toFixed(0)})` : "—"}
                          </TableCell>
                          <TableCell className="font-mono text-[11px] text-muted-foreground">
                            {d.te ? `(${d.te.xMm.toFixed(0)}, ${d.te.zMm.toFixed(0)})` : "—"}
                          </TableCell>
                          <TableCell className="max-w-[180px] truncate text-xs text-muted-foreground" title={d.notes}>
                            {d.notes || d.cadName || "—"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          )}

          <CarSchematic />

          <Card>
            <CardHeader>
              <CardTitle>Jakość numeryczna case</CardTitle>
              <CardDescription>
                Wartości zbieżności i siatki warunkujące zaufanie do liczb
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-2 font-mono text-xs sm:grid-cols-2">
              <p>
                continuity:{" "}
                {fluentCase.residuals.continuity == null
                  ? "brak"
                  : fluentCase.residuals.continuity.toExponential(2)}
              </p>
              <p>
                x-mom:{" "}
                {fluentCase.residuals.xMomentum == null
                  ? "brak"
                  : fluentCase.residuals.xMomentum.toExponential(2)}
              </p>
              <p>
                y+ skrzydła: avg {fmtNum(fluentCase.yPlusWings?.avg, 2)} (max{" "}
                {fmtNum(fluentCase.yPlusWings?.max, 2)})
              </p>
              <p>y+ podłoga: avg {fmtNum(fluentCase.yPlusFloor?.avg, 2)}</p>
              <p>model: {fluentCase.turbulence}</p>
              <p>warstwa: {fluentCase.wallTreatment}</p>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 4: Agent pack */}
        <TabsContent value="pack" className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="max-w-2xl text-sm text-muted-foreground">
              To jest właściwy kontrakt z agentem: ustrukturyzowany prompt + {heroes.length} hero klatek +
              narzędzia tool-calling. Surowe pliki .cas/.dat zostają na maszynie inżyniera.
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowRawJson(!showRawJson)}
                className="gap-1.5"
              >
                <Code2 className="size-3.5" />
                {showRawJson ? "Pokaż prompt" : "Pokaż surowy JSON"}
              </Button>
              <Button size="sm" onClick={copyPack} className="gap-1.5">
                {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
                {copied ? "Skopiowane" : "Kopiuj prompt"}
              </Button>
            </div>
          </div>
          <pre className="max-h-[540px] overflow-auto rounded-xl bg-[#07090d] p-4 text-[11px] leading-relaxed text-[#c5d0de] ring-1 ring-white/10">
            {showRawJson ? JSON.stringify(packData.rawPack, null, 2) : prompt}
          </pre>
        </TabsContent>

        {/* Tab 5: Ocena */}
        <TabsContent value="ocena" className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <Badge className="h-7 rounded-md bg-[#f4c14d] px-3 text-[#1a1406]">
              {VERDICT_LABEL[review.verdict]}
            </Badge>
            <span className="text-sm text-muted-foreground">
              silnik reguł aero FS — twarda ocena numeryczna i geometryczna
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={async () => {
                if (selectedPackId === "demo-fs26" || selectedPackId === "custom") {
                  setAskText("Siły z dysku są dostępne dla paczki wczytanej z folderu packs.")
                  return
                }
                const res = await fetch(`/api/ask?id=${encodeURIComponent(selectedPackId)}&tool=forces`)
                const data = await res.json()
                setAskText(JSON.stringify(data, null, 2))
              }}
            >
              Daj siły tej paczki
            </Button>
          </div>
          {askText ? (
            <pre className="max-h-48 overflow-auto rounded-md border bg-muted/40 p-3 text-xs">{askText}</pre>
          ) : null}
          <p className="max-w-3xl text-sm leading-relaxed">{review.summary}</p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <ScoreBar label="zbieżność" value={review.scores.zbieznosc} />
            <ScoreBar label="siatka / y+" value={review.scores.siatka} />
            <ScoreBar label="L/D" value={review.scores.wydajnosc} />
            <ScoreBar label="balans" value={review.scores.balanse} />
            <ScoreBar label="pokrycie klatek" value={review.scores.pokrycieWizualne} />
          </div>
          <div className="space-y-3">
            {review.findings.map((f) => (
              <Card key={f.id}>
                <CardHeader>
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`rounded-md border px-2 py-0.5 text-[11px] uppercase ${SEVERITY_CLASS[f.severity]}`}
                    >
                      {f.severity}
                    </span>
                    <CardTitle>{f.title}</CardTitle>
                  </div>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  <p>
                    <span className="text-muted-foreground">Dowód: </span>
                    {f.evidence}
                  </p>
                  <p>
                    <span className="text-muted-foreground">Rekomendacja: </span>
                    {f.recommendation}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Pytania do inżyniera</CardTitle>
              </CardHeader>
              <CardContent>
                <ol className="list-decimal space-y-2 pl-4 text-sm">
                  {review.questions.map((q, idx) => (
                    <li key={idx}>{q}</li>
                  ))}
                </ol>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Kolejne runy (następne iteracje)</CardTitle>
              </CardHeader>
              <CardContent>
                <ol className="list-decimal space-y-2 pl-4 text-sm">
                  {review.nextRuns.map((r, idx) => (
                    <li key={idx}>{r}</li>
                  ))}
                </ol>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
