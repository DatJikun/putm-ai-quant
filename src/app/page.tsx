import Link from "next/link"
import { sources, verdict } from "@/lib/research"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { ArrowRight } from "lucide-react"

const LAYERS = [
  {
    n: "01",
    title: "Liczby z solvera, nie z pikseli",
    body: ".cas/.dat (najlepiej CFF .cas.h5/.dat.h5) → Cl, Cd, Cs, momenty, siły po strefach, residuale, y+, Aref, V∞, model turbulencji. PyFluent FileSession albo FluentCFFReader. Stary binarny .cas bez HDF5: wyeksportuj EnSight/VTK albo odpal Fluent headless raz i zrzuc raporty.",
  },
  {
    n: "02",
    title: "CAD jako linijka, nie jako ozdoba",
    body: "STEP/STL → rozstaw osi, track, ride height, rake, lista części, pole czołowe. Agent musi wiedzieć, że X=0.70 m to oś przednia, a nie „jakiś przekrój”. Bez tego 1500 klatek to tapeta.",
  },
  {
    n: "03",
    title: "Katalog 1500 → 15–30 hero",
    body: "Nazwa pliku musi kodować oś, stację, pole, kamerę. Potem selector: FW, oś przednia, wlot podłogi, hoop, dyfuzor, RW, bliski i daleki ślad. Reszta zostaje w indeksie — VLM może dopytać, nie żre dumpa.",
  },
  {
    n: "04",
    title: "Agent z narzędziami, nie z jednym promptem",
    body: "Pierwszy strzał: JSON + hero PNG. Drugi: tool „daj X=2.30 m Cp total”. Trzeci: porównaj z baseline. Tak robi AI CFD Scientist (vision gate) i Navier. Sam chat z 1500 załącznikami jest drogi i kłamie pewnością.",
  },
]

export default function HomePage() {
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-10">
      <p className="font-mono text-[11px] tracking-[0.22em] text-[#5ee0c0] uppercase">
        research + prototyp packa
      </p>
      <h1 className="mt-3 max-w-4xl text-4xl font-medium tracking-tight text-balance sm:text-5xl">
        Tak — da się to skwantyfikować i dać agentowi. Nie jako 1500 zdjęć i surowe pliki Fluent.
      </h1>
      <p className="mt-5 max-w-3xl text-base leading-relaxed text-muted-foreground">
        Rozumiem setup: wynik Fluent (.cas + .dat), batch post-processingu całego
        bolidu oraz płaszczyzn X/Y/Z (u Ciebie rzędu 1500 PNG) i oryginalny model
        auta. Cel: recenzja aero, nie ładny slideshow. Nikt nie opublikował
        gotowego klonu „Fluent Formula Student + 1500 klatek + CAD → jeden agent”,
        ale kawałki już istnieją. Poniżej werdykt, literatura i propozycja, którą
        da się kliknąć w warsztacie.
      </p>
      <div className="mt-8 flex flex-wrap gap-3">
        <Button render={<Link href="/warsztat" />}>
          Otwórz warsztat demo
          <ArrowRight />
        </Button>
        <Button variant="outline" render={<a href="#zrodla" />}>
          12 źródeł z internetu
        </Button>
      </div>

      <section className="mt-14 grid gap-3 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardDescription>Czy rozumiem</CardDescription>
            <CardTitle>Tak, 1:1</CardTitle>
          </CardHeader>
          <CardContent className="text-sm leading-relaxed text-muted-foreground">
            Fluent trzyma siatkę i pola. Zdjęcia to tylko rzuty. CAD mówi, gdzie
            jest skrzydło i ziemia. Agent bez tych trzech warstw albo zgaduje z
            colormapy, albo dusi się tokenami.
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Czy ktoś to zrobił</CardDescription>
            <CardTitle>Kawałki, nie klon FS</CardTitle>
          </CardHeader>
          <CardContent className="text-sm leading-relaxed text-muted-foreground">
            Navier recenzuje CFD. AI CFD Scientist ogląda PNG i łapie ciche błędy.
            Zespoły FS automatyzują dump (Tampere, WAK, MDPI+Fluent). Brakuje
            otwartego packa pod Twoje cas/dat.
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Czy wrzucać dump</CardDescription>
            <CardTitle>Nie. Pack.</CardTitle>
          </CardHeader>
          <CardContent className="text-sm leading-relaxed text-muted-foreground">
            {verdict.doNotDumpRaw}
          </CardContent>
        </Card>
      </section>

      <section className="mt-16">
        <h2 className="text-2xl font-medium tracking-tight">
          Co ja bym zrobił z Twoimi plikami
        </h2>
        <ol className="mt-6 grid gap-4">
          {LAYERS.map((layer) => (
            <li
              key={layer.n}
              className="grid gap-2 rounded-xl border border-white/10 bg-card p-5 md:grid-cols-[4rem_1fr] md:items-start"
            >
              <span className="font-mono text-sm text-[#5ee0c0]">{layer.n}</span>
              <div>
                <h3 className="font-medium">{layer.title}</h3>
                <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                  {layer.body}
                </p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="mt-16">
        <h2 className="text-2xl font-medium tracking-tight">
          Czego agentowi nie wolno obiecywać
        </h2>
        <ul className="mt-4 max-w-3xl space-y-2 text-sm leading-relaxed text-muted-foreground">
          <li>
            Że z PNG odczyta dokładne Cl — colormap jest zła do metrologii.
            Liczby tylko z raportu sił.
          </li>
          <li>
            Że „widzi separację” na jednej klatce. Musi złożyć X (ślad koła) + Z
            (podłoga) + udział komponentu.
          </li>
          <li>
            Że 18 mln komórek w .dat zmieści się w kontekście. Nie zmieści się.
            Redukuj do stref i próbek.
          </li>
          <li>
            Że yaw 0° wystarczy do slalomu FS. Pack sezonu to mapa V∞ × yaw ×
            ride height, nie jeden ładny case.
          </li>
        </ul>
      </section>

      <section id="zrodla" className="mt-16 scroll-mt-20">
        <h2 className="text-2xl font-medium tracking-tight">
          Co znalazłem w internecie
        </h2>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Szukałem recenzji CFD przez LLM/VLM, readerów Fluent, automatycznego
          post-processingu i konkretnie Formula Student / FSAE.
        </p>
        <div className="mt-6 grid gap-3">
          {sources.map((s) => (
            <a
              key={s.url}
              href={s.url}
              target="_blank"
              rel="noreferrer"
              className="block rounded-xl border border-white/10 bg-card p-4 transition hover:border-[#5ee0c0]/40"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="font-medium">{s.title}</h3>
                <span className="font-mono text-[11px] text-[#5ee0c0]">
                  {s.overlap} · {s.year}
                </span>
              </div>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                {s.what}
              </p>
            </a>
          ))}
        </div>
      </section>

      <section className="mt-16 mb-8 rounded-2xl border border-[#5ee0c0]/30 bg-[#5ee0c0]/5 p-6">
        <h2 className="text-xl font-medium">Następny krok na Twoich danych</h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted-foreground">
          Daj folder: .cas.h5/.dat.h5 (albo CSV z report definitions), STEP/STL,
          zdjęcia z konwencją nazw <code className="text-foreground">oś_stacja_pole.png</code>.
          Wtedy pack przestaje być syntetyczny. Demo obok pokazuje, jak ten pack
          ma wyglądać i jakiego recenzenta warto na nim puścić.
        </p>
        <Button className="mt-4" render={<Link href="/warsztat" />}>
          Zobacz pack na FS-26
          <ArrowRight />
        </Button>
      </section>
    </div>
  )
}
