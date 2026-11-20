import { StudioView } from "@/components/studio-view";

export default async function StudioPage({ params }: { params: Promise<{ spaceId: string }> }) {
  const { spaceId } = await params;
  return <StudioView spaceId={spaceId} />;
}
