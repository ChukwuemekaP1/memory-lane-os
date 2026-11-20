import { Suspense } from "react";

import { SpaceProvider } from "@/components/space-provider";

export default async function SpaceLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ spaceId: string }>;
}) {
  const { spaceId } = await params;
  return (
    <Suspense
      fallback={
        <main className="mx-auto w-full max-w-xl px-6 py-16">
          <p role="status" className="text-sm opacity-70">
            Loading this memory space…
          </p>
        </main>
      }
    >
      <SpaceProvider spaceId={spaceId}>{children}</SpaceProvider>
    </Suspense>
  );
}
