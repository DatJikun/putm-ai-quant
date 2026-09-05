"use client"

import { useMemo, useState } from "react"
import {
  AXIS_LABEL,
  FIELD_LABEL,
  REGION_LABEL,
  catalogStats,
} from "@/lib/catalog"
import { cad, fluentCase, getDemoImages, kpis, reynolds } from "@/lib/demo-case"
import { evaluateCase, VERDICT_LABEL } from "@/lib/agent"
import { buildAgentPack, packAsPrompt } from "@/lib/pack"
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
import { Check, Copy } from "lucide-react"

const PAGE = 25

const SEVERITY_CLASS: Record<Severity, string> = {
  info: "border-[#5ee0c0]/40 bg-[#5ee0c0]/10 text-[#9af0dc]",
  watch: "border-amber-400/40 bg-amber-400/10 text-amber-200",
  issue: "border-orange-500/40 bg-orange-500/10 text-orange-200",
  blocker: "border-red-500/50 bg-red-500/10 text-red-200",
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>{label}</span>
        <span className="font-mono text-foreground">{value}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
        <div
          className="h-full rounded-full bg-[#5ee0c0]"
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  )
}

export function Workbench() {
  const images = useMemo(() => getDemoImages(), [])
  const stats = useMemo(() => catalogStats(images), [images])
  const review = useMemo(
    () => evaluateCase(fluentCase, kpis, cad, images),
    [images],
  )
  const pack = useMemo(
    () => buildAgentPack(fluentCase, cad, kpis, images),
    [images],
  )
  const prompt = useMemo(() => packAsPrompt(pack), [pack])
  const heroes = useMemo(() => images.filter((i) => i.hero), [images])

  const [axis, setAxis] = useState<Axis | "all">("all")
  const [field, setField] = useState<FieldId | "all">("all")
  const [heroOnly, setHeroOnly] = useState(false)
  const [page, setPage] = useState(0)
  const [copied, setCopied] = useState(false)
  const [selectedHero, setSelectedHero] = useState(heroes[0]?.id ?? "")

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
  const selected = heroes.find((h) => h.id === selectedHero) ?? heroes[0]

  async function copyPack() {
    await navigator.clipboard.writeText(prompt)
    setCopied(true)
    setTimeout(() => setCopied(false), 1600)
  }

  return (
    <Tabs defaultValue="zrodla" className="gap-5">
      <TabsList variant="line" className="w-full flex-wrap justify-start">
        <TabsTrigger value="zrodla">1. Źródła</TabsTrigger>
        <TabsTrigger value="katalog">2. Katalog 1500</TabsTrigger>
        <TabsTrigger value="kpi">3. Liczby + CAD</TabsTrigger>
        <TabsTrigger value="pack">4. Agent pack</TabsTrigger>
        <TabsTrigger value="ocena">5. Ocena</TabsTrigger>
      </TabsList>

      <TabsContent value="zrodla" className="space-y-4">
        <div className="grid gap-3 md:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle>Fluent</CardTitle>
              <CardDescription>to, czego agent nie powinien łykać w całości</CardDescription>
            </CardHeader>
            <CardContent className="space-y-1 font-mono text-xs">
              <p>{fluentCase.casFile}</p>
              <p>{fluentCase.datFile}</p>
              <p className="pt-2 text-muted-foreground">
                {fluentCase.solver}
              </p>
              <p>{fluentCase.cellsM} mln komórek · {fluentCase.iterations} iter.</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>CAD</CardTitle>
              <CardDescription>kotwica stacji i komponentów</CardDescription>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              <p className="font-mono text-xs">{cad.name}</p>
              <p>
                {cad.wheelbaseMm} mm wb · A = {cad.frontalAreaM2} m²
              </p>
              <p>
                RH {cad.rideHeightFrontMm}/{cad.rideHeightRearMm} mm · rake{" "}
                {cad.rakeDeg}°
              </p>
              <p className="text-xs text-muted-foreground">
                {cad.triangles.toLocaleString("pl-PL")} trójkątów powierzchni
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Post-processing</CardTitle>
              <CardDescription>dump klatek jak z CFD-Post batch</CardDescription>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              <p>
                <span className="font-mono text-lg text-[#5ee0c0]">
                  {stats.total}
                </span>{" "}
                PNG
              </p>
              <p>full {stats.byAxis.full} · X {stats.byAxis.x}</p>
              <p>Y {stats.byAxis.y} · Z {stats.byAxis.z}</p>
              <p className="text-xs text-muted-foreground">
                {stats.heroCount} hero do VLM, reszta to indeks
              </p>
            </CardContent>
          </Card>
        </div>
        <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground">
          Demo nie otwiera prawdziwego Fluenta — liczby i 1500 rekordów katalogu
          są syntetyczne, ale w tej samej strukturze, którą wyciągniesz z
          PyFluent FileSession / raportów sił + nazewnictwa batcha CFD-Post.
          Kontury niżej są znacznikami stacji, nie wynikiem solvera.
        </p>
      </TabsContent>

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
              <CardTitle>Indeks, nie galeria</CardTitle>
              <CardDescription>
                Agent dostaje ten rejestr. PNG idą tylko gdy wiersz jest hero albo gdy sam o nie poprosi.
              </CardDescription>
            </CardHeader>
            <CardContent>
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
                      <TableCell className="max-w-[180px] truncate font-mono text-[11px]">
                        {img.hero ? "★ " : ""}
                        {img.filename}
                      </TableCell>
                      <TableCell>{img.axis}</TableCell>
                      <TableCell>{FIELD_LABEL[img.field]}</TableCell>
                      <TableCell className="font-mono">
                        {img.stationM == null ? "—" : `${img.stationM.toFixed(2)} m`}
                      </TableCell>
                      <TableCell>{REGION_LABEL[img.region]}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
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
              Hero klatki — to jedyne obrazy, które idą do VLM w pierwszym strzale.
            </p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {heroes.map((h) => (
                <button
                  key={h.id}
                  type="button"
                  onClick={() => setSelectedHero(h.id)}
                  className={`overflow-hidden rounded-lg ring-1 ${
                    selected?.id === h.id
                      ? "ring-[#5ee0c0]"
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
            {selected && (
              <p className="text-sm leading-relaxed">
                <span className="font-medium text-[#5ee0c0]">
                  {REGION_LABEL[selected.region]}
                </span>
                {" — "}
                {selected.reason}
              </p>
            )}
          </div>
        </div>
      </TabsContent>

      <TabsContent value="kpi" className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ["Cl (downforce)", kpis.Cl.toFixed(2)],
            ["Cd", kpis.Cd.toFixed(2)],
            ["L/D", kpis.LOverD.toFixed(2)],
            ["balans przód", `${kpis.frontBalancePct} %`],
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
          {kpis.downforceN.toFixed(0)} N downforce / {kpis.dragN.toFixed(0)} N
          drag przy {fluentCase.speedMs} m/s · Re ≈{" "}
          {(reynolds() / 1e6).toFixed(2)}×10<sup>6</sup>
        </p>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>komponent</TableHead>
              <TableHead>Cl</TableHead>
              <TableHead>Cd</TableHead>
              <TableHead>% DF</TableHead>
              <TableHead>% drag</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {kpis.components.map((c) => (
              <TableRow key={c.name}>
                <TableCell>{c.name}</TableCell>
                <TableCell className="font-mono">{c.Cl.toFixed(2)}</TableCell>
                <TableCell className="font-mono">{c.Cd.toFixed(2)}</TableCell>
                <TableCell>{c.shareDownforcePct}%</TableCell>
                <TableCell>{c.shareDragPct}%</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <CarSchematic />
        <Card>
          <CardHeader>
            <CardTitle>Jakość case</CardTitle>
            <CardDescription>
              To też idzie do packa — bez tego VLM ufa ładnym obrazkom
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-2 font-mono text-xs sm:grid-cols-2">
            <p>continuity {fluentCase.residuals.continuity.toExponential(2)}</p>
            <p>x-mom {fluentCase.residuals.xMomentum.toExponential(2)}</p>
            <p>
              y+ skrzydła avg {fluentCase.yPlusWings.avg} (max{" "}
              {fluentCase.yPlusWings.max})
            </p>
            <p>y+ podłoga avg {fluentCase.yPlusFloor.avg}</p>
            <p>{fluentCase.turbulence}</p>
            <p>{fluentCase.wallTreatment}</p>
          </CardContent>
        </Card>
      </TabsContent>

      <TabsContent value="pack" className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="max-w-2xl text-sm text-muted-foreground">
            To jest kontrakt z agentem: JSON + {heroes.length} obrazków +
            instrukcja. Surowe .cas/.dat zostają na dysku inżyniera.
          </p>
          <Button onClick={copyPack}>
            {copied ? <Check /> : <Copy />}
            {copied ? "skopiowane" : "kopiuj prompt"}
          </Button>
        </div>
        <pre className="max-h-[520px] overflow-auto rounded-xl bg-[#07090d] p-4 text-[11px] leading-relaxed text-[#c5d0de] ring-1 ring-white/10">
          {prompt}
        </pre>
      </TabsContent>

      <TabsContent value="ocena" className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <Badge className="h-7 rounded-md bg-[#f4c14d] px-3 text-[#1a1406]">
            {VERDICT_LABEL[review.verdict]}
          </Badge>
          <span className="text-sm text-muted-foreground">
            silnik reguł aero FS — ten sam werdykt, który VLM powinien umieć
            uzasadnić obrazkami
          </span>
        </div>
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
                  <span className="text-muted-foreground">Rób: </span>
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
                {review.questions.map((q) => (
                  <li key={q}>{q}</li>
                ))}
              </ol>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Kolejne runy</CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="list-decimal space-y-2 pl-4 text-sm">
                {review.nextRuns.map((q) => (
                  <li key={q}>{q}</li>
                ))}
              </ol>
            </CardContent>
          </Card>
        </div>
      </TabsContent>
    </Tabs>
  )
}
