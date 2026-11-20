import { MemoryFeed } from "@/components/memory-feed";

export default async function GalleryPage({ params }: { params: Promise<{ spaceId: string }> }) {
  const { spaceId } = await params;
  return <MemoryFeed spaceId={spaceId} mediaOnly />;
}
