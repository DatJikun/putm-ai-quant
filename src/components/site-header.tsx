import Link from "next/link"
import { BoxSelect } from "lucide-react"

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-white/10 bg-[#07090d]/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
        <Link href="/" className="flex items-center gap-2 font-medium tracking-tight">
          <BoxSelect className="size-4 text-[#5ee0c0]" />
          <span>AeroPack</span>
          <span className="hidden text-xs text-muted-foreground sm:inline">
            recenzja CFD bolidu FS
          </span>
        </Link>
        <nav className="flex items-center gap-1 text-sm">
          <Link
            href="/"
            className="rounded-md px-3 py-1.5 text-muted-foreground hover:bg-white/5 hover:text-foreground"
          >
            Werdykt
          </Link>
          <Link
            href="/warsztat"
            className="rounded-md bg-[#5ee0c0] px-3 py-1.5 font-medium text-[#07221c] hover:bg-[#7aead0]"
          >
            Warsztat demo
          </Link>
        </nav>
      </div>
    </header>
  )
}
