import { TimelineView } from "@/components/timeline-view";

export default async function TimelinePage({ params }: { params: Promise<{ spaceId: string }> }) {
  const { spaceId } = await params;
  return <TimelineView spaceId={spaceId} />;
}
