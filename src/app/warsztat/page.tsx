import { Workbench } from "@/components/workbench"

export const metadata = {
  title: "Pakiety — AeroPack",
  description:
    "Przeglądarka pakietów: wnioski, wiarygodność, siły z Fluenta, przekroje i porównanie symulacji.",
}

export default function WarsztatPage() {
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-8">
      <p className="font-mono text-[11px] tracking-[0.2em] text-[#5ee0c0] uppercase">
        pakiety z folderu packs/ · yaw 0° · 15 m/s
      </p>
      <h1 className="mt-2 max-w-3xl text-3xl font-medium tracking-tight">
        Pakiety symulacji: wnioski, liczby i obrazy z plików Fluenta
      </h1>
      <p className="mt-3 mb-8 max-w-2xl text-sm leading-relaxed text-muted-foreground">
        Wybierz symulację z listy. Obrazy w katalogu są robione z plików .cas.h5 i .dat.h5,
        a „Syntetyczny FS-26” na liście to tylko przykład z udawanymi danymi.
      </p>
      <Workbench />
    </div>
  )
}
