import { RestaurantOverview } from "@/components/dashboard";
import { Shell } from "@/components/shell";
import { requireRestaurant } from "@/lib/session";

export default async function Page({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const user = await requireRestaurant(slug, "dashboard", "dashboard.view");
  return <Shell user={user}><RestaurantOverview slug={slug} /></Shell>;
}
