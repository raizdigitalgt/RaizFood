import { Resume } from "@/components/auth";

export default async function SessionPage({ searchParams }: {
  searchParams: Promise<{ next?: string }>;
}) {
  const { next } = await searchParams;
  const destination = next && /^\/(platform\/[a-z-]+(?:\/[a-z0-9-]+)?|app\/[a-z0-9-]+\/[a-z]+|restaurantes)$/.test(next)
    ? next : undefined;
  return <Resume destination={destination} />;
}
