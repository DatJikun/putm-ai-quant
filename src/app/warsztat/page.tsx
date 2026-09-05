import { Workbench } from "@/components/workbench"

export const metadata = {
  title: "Warsztat — AeroPack",
  description:
    "Demo packa: 1500 klatek CFD, KPI z Fluenta, CAD bolidu i recenzja agenta.",
}

export default function WarsztatPage() {
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-8">
      <p className="font-mono text-[11px] tracking-[0.2em] text-[#5ee0c0] uppercase">
        demo case FS-26 · yaw 0° · 15 m/s
      </p>
      <h1 className="mt-2 max-w-3xl text-3xl font-medium tracking-tight">
        Od dumpa do packa, który agent ma prawo oceniać
      </h1>
      <p className="mt-3 mb-8 max-w-2xl text-sm leading-relaxed text-muted-foreground">
        Pięć kroków na syntetycznym bolidzie Formula Student. Te same pola
        wypełnisz z .cas.h5/.dat.h5, STEP-a i batcha zdjęć.
      </p>
      <Workbench />
    </div>
  )
}
