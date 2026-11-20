import { Suspense } from "react";

import { CurationCockpit } from "@/components/curation-cockpit";

export default async function SettingsPage({ params }: { params: Promise<{ spaceId: string }> }) {
  const { spaceId } = await params;
  return (
    <Suspense fallback={<div className="site-frame py-12 text-sm opacity-70">Loading curation cockpit…</div>}>
      <CurationCockpit spaceId={spaceId} />
    </Suspense>
  );
}
