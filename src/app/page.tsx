import Link from "next/link"
import { listPacks } from "@/lib/pack-list"
import { buttonVariants } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { ArrowRight } from "lucide-react"

export const dynamic = "force-dynamic"

const STEPS = [
  {
    n: "1",
    title: "Pliki z Fluenta wchodzą",
    body: "Folder symulacji: .cas.h5, .dat.h5, .msh.h5 i model .step. Nie są potrzebne ani pliki CFD-Post, ani zrzuty ekranu, ani logi .trn/.out.",
  },
  {
    n: "2",
    title: "Wychodzi jeden mały metaplik",
    body: "Siły i docisk po częściach auta, residua i bilans masy, mapy ciśnienia i tarcia na ścianie w dwóch rozdzielczościach (1 cm i 3 mm), przekroje przepływu co 2 cm oraz wnioski i ocena wiarygodności. Zamiast kilkudziesięciu GB zostaje kilkanaście MB.",
  },
  {
    n: "3",
    title: "Z metapliku da się wyciągać wnioski",
    body: "Przeglądarka, dokumenty skrótowy i pełny, porównanie dwóch symulacji z odpowiedzią na pytanie „dlaczego docisk się zmienił” oraz serwer MCP, przez który pyta chatbot.",
  },
]

const COMMANDS: readonly [string, string][] = [
  ["python -m ingest report <folder>", "dokumenty SKROT i PELNY, obrazy, ocena wiarygodności"],
  ["python -m ingest meta <folder>", "metaplik z mapami 1 cm i 3 mm oraz przekrojami"],
  ["python -m ingest compare <A> <B>", "porównanie dwóch lub więcej symulacji, razem z sekcją „Dlaczego się zmieniło”"],
  ["python -m ingest why <A> <B>", "samo wyjaśnienie zmiany docisku i oporu, część po części"],
  ["python -m ingest viewer <folder>", "eksport do przeglądarki 3D przepływu (CFD3DViewer)"],
]

export default async function HomePage() {
  const packs = await listPacks()
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-10">
      <p className="font-mono text-[11px] tracking-[0.22em] text-[#5ee0c0] uppercase">stan projektu</p>
      <h1 className="mt-3 max-w-4xl text-4xl font-medium tracking-tight text-balance sm:text-5xl">
        Wyniki Fluenta zamienione na mały plik, z którego da się szybko wyciągać wnioski.
      </h1>
      <p className="mt-5 max-w-3xl text-base leading-relaxed text-muted-foreground">
        To narzędzie czyta symulacje z plików modelu i zastępuje pliki CFD-Post oraz zdjęcia z post-processingu
        liczbami, mapami i opisanymi wnioskami. Każda liczba ma wskazane źródło, a ocena wiarygodności mówi też,
        czego nie udało się sprawdzić.
      </p>
      <div className="mt-8 flex flex-wrap gap-3">
        <Link href="/warsztat" className={cn(buttonVariants())}>
          Otwórz przeglądarkę pakietów
          <ArrowRight />
        </Link>
      </div>

      <section className="mt-14">
        <h2 className="text-2xl font-medium tracking-tight">Symulacje na tym komputerze</h2>
        {packs.length === 0 ? (
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
            Folder <span className="font-mono">packs/</span> jest pusty. Zrób pakiet poleceniem{" "}
            <span className="font-mono">python -m ingest report &lt;folder symulacji&gt;</span>, a pojawi się tutaj.
          </p>
        ) : (
          <div className="mt-5 grid gap-3 md:grid-cols-2">
            {packs.map((p) => (
              <Card key={p.id}>
                <CardHeader>
                  <CardDescription className="font-mono text-xs">{p.id}</CardDescription>
                  <CardTitle>{p.name}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-1.5 text-sm">
                  {p.hasMeta ? (
                    <>
                      <p className="font-medium text-[#f4c14d]">{p.verdict ?? "Brak werdyktu"}</p>
                      <p className="text-muted-foreground">
                        Wiarygodność: {p.credibilityScore == null ? "brak oceny" : `${p.credibilityScore}/100`} ·{" "}
                        {p.findingsCount} wniosków
                      </p>
                    </>
                  ) : (
                    <p className="text-muted-foreground">
                      Bez metapliku. Dołóż go poleceniem <span className="font-mono">python -m ingest meta</span>.
                    </p>
                  )}
                  <p className="text-xs text-muted-foreground">
                    {(p.cells / 1e6).toFixed(1)} mln komórek · {p.imagesTotal} klatek w indeksie
                    {p.warningsCount > 0 ? ` · ${p.warningsCount} ostrzeżeń` : ""}
                  </p>
                  <Link
                    href="/warsztat"
                    className="inline-block pt-1 text-xs text-[#5ee0c0] underline underline-offset-2"
                  >
                    Otwórz w przeglądarce
                  </Link>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section className="mt-14">
        <h2 className="text-2xl font-medium tracking-tight">Jak to działa</h2>
        <ol className="mt-5 grid gap-4">
          {STEPS.map((step) => (
            <li
              key={step.n}
              className="grid gap-2 rounded-xl border border-white/10 bg-card p-5 md:grid-cols-[3rem_1fr] md:items-start"
            >
              <span className="font-mono text-sm text-[#5ee0c0]">{step.n}</span>
              <div>
                <h3 className="font-medium">{step.title}</h3>
                <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{step.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="mt-14">
        <h2 className="text-2xl font-medium tracking-tight">Polecenia</h2>
        <ul className="mt-4 space-y-2">
          {COMMANDS.map(([command, what]) => (
            <li key={command} className="grid gap-1 text-sm md:grid-cols-[22rem_1fr]">
              <code className="text-foreground">{command}</code>
              <span className="text-muted-foreground">{what}</span>
            </li>
          ))}
        </ul>
        <p className="mt-4 max-w-3xl text-xs leading-relaxed text-muted-foreground">
          Zgodność z rzeczywistością da się ocenić tylko z pomiarów. Do tego służy plik{" "}
          <span className="font-mono">pomiary.json</span>. Bez niego ocena obejmuje wyłącznie jakość obliczeń i
          porównanie z literaturą. Pełny opis jest w <span className="font-mono">JAK-TO-DZIALA.md</span>.
        </p>
      </section>
    </div>
  )
}
