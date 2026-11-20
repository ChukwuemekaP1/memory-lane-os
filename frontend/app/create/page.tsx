import { redirect } from "next/navigation";

export default async function LegacyCreateRedirectPage({
  searchParams,
}: {
  searchParams: Promise<{ occasion?: string }>;
}) {
  const params = await searchParams;
  const occasion = params?.occasion ? `?occasion=${encodeURIComponent(params.occasion)}` : "";
  redirect(`/app/create${occasion}`);
}
