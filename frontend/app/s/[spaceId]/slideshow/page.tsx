import { SlideshowView } from "@/components/slideshow-view";

export default async function SlideshowPage({ params }: { params: Promise<{ spaceId: string }> }) {
  const { spaceId } = await params;
  return <SlideshowView spaceId={spaceId} />;
}
