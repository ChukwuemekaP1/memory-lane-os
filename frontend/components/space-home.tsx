"use client";

import { MemoryFeed } from "@/components/memory-feed";
import { SpaceCoverBand } from "@/components/space-provider";

export function SpaceHome({ spaceId }: { spaceId: string }) {
  return (
    <div>
      <SpaceCoverBand spaceId={spaceId} />
      <MemoryFeed spaceId={spaceId} mediaOnly={false} />
    </div>
  );
}
