import { Resume } from "@/components/auth";

export default async function SessionPage({ searchParams }: {
  searchParams: Promise<{ next?: string }>;
}) {
  const { next } = await searchParams;
  const basic = /^\/(platform\/[a-z-]+(?:\/[a-z0-9-]+)?|app\/[a-z0-9-]+\/[a-z-]+|restaurantes)$/;
  const pos = /^\/app\/[a-z0-9-]+\/pos\?(?:new=1|(?:order|table)=[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})$/;
  const destination = next && (basic.test(next) || pos.test(next)) ? next : undefined;
  return <Resume destination={destination} />;
}
