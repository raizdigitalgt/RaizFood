import { Restaurants } from "@/components/dashboard";
import { Shell } from "@/components/shell";
import { requirePlatform } from "@/lib/session";

export default async function Page({ searchParams }: { searchParams: Promise<{ new?: string }> }) {
  const user = await requirePlatform("/platform/restaurants", "restaurants");
  return <Shell user={user}><Restaurants open={(await searchParams).new === "1"} /></Shell>;
}
