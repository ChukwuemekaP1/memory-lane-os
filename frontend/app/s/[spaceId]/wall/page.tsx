import { WallView } from "@/components/wall-view";

export default async function WallPage({ params }: { params: Promise<{ spaceId: string }> }) {
  const { spaceId } = await params;
  return <WallView spaceId={spaceId} />;
}
