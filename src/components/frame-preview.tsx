import { frameImageUrl, type Gallery } from "@/lib/meta"
import type { PostImage } from "@/lib/types"
import { ContourPreview } from "@/components/contour-preview"

/**
 * A frame from the catalogue. A real pack shows our own picture made from the Fluent files
 * (a plane at the nearest position, or a wall view); when there is none it says so
 * instead of drawing something that looks like a result.
 */
export function FramePreview({
  packId,
  gallery,
  image,
  isDemo,
}: {
  packId: string
  gallery: Gallery | null
  image: PostImage
  isDemo: boolean
}) {
  if (isDemo) {
    return <ContourPreview id={image.id} axis={image.axis} field={image.field} stationM={image.stationM} />
  }
  const url = frameImageUrl(packId, gallery, image.axis, image.field, image.stationM, image.camera)
  const title =
    image.stationM == null
      ? `${image.field} · ${image.axis}`
      : `${image.field} · ${image.axis} = ${image.stationM.toFixed(2)} m`
  if (!url) {
    return (
      <div className="flex aspect-[5/3] flex-col items-center justify-center gap-1 bg-[#07090d] p-2 text-center">
        <span className="font-mono text-[10px] text-muted-foreground">{title}</span>
        <span className="text-[10px] text-muted-foreground/70">brak własnego obrazu tej klatki</span>
      </div>
    )
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element -- pictures come from a local route, not an optimizable remote source
    <img src={url} alt={title} loading="lazy" className="aspect-[5/3] w-full bg-[#07090d] object-contain" />
  )
}
