import { ContributeForm } from "@/components/contribute-form";

export default async function ContributePage({ params }: { params: Promise<{ spaceId: string }> }) {
  const { spaceId } = await params;
  return <ContributeForm spaceId={spaceId} />;
}
