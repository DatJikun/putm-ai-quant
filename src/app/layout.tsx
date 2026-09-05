import type { Metadata } from "next"
import { Geist, Geist_Mono } from "next/font/google"
import { SiteHeader } from "@/components/site-header"
import { TooltipProvider } from "@/components/ui/tooltip"
import "./globals.css"

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin", "latin-ext"],
})

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin", "latin-ext"],
})

export const metadata: Metadata = {
  title: "AeroPack — recenzja CFD bolidu Formula Student",
  description:
    "Jak skwantyfikować wyniki Fluent (.cas/.dat), 1500 klatek post-processingu i model CAD, żeby agent AI mógł ocenić aero bolidu FS.",
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="pl"
      className={`dark ${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col bg-background text-foreground">
        <TooltipProvider>
          <SiteHeader />
          <main className="flex-1">{children}</main>
        </TooltipProvider>
      </body>
    </html>
  )
}
