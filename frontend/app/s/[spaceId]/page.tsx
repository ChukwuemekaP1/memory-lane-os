import { SpaceHome } from "@/components/space-home";

export default async function SpaceHomePage({ params }: { params: Promise<{ spaceId: string }> }) {
  const { spaceId } = await params;
  return <SpaceHome spaceId={spaceId} />;
}
