import { RestaurantView } from "@/components/platform/commerce";
import { Shell } from "@/components/shell";
import { requirePlatform } from "@/lib/session";

export default async function Page({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const user = await requirePlatform(`/platform/restaurants/${slug}`, "restaurants");
  return <Shell user={user}><RestaurantView slug={slug} subscriptionAccess={user.platform_permissions.includes("subscriptions")} /></Shell>;
}
