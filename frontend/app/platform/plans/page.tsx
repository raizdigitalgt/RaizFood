import { PlanCatalog } from "@/components/platform/commerce";
import { Shell } from "@/components/shell";
import { requirePlatform } from "@/lib/session";

export default async function Page({ searchParams }: { searchParams: Promise<{ new?: string }> }) {
  const user = await requirePlatform("/platform/plans", "plans");
  return <Shell user={user}><PlanCatalog open={(await searchParams).new === "1"} /></Shell>;
}
