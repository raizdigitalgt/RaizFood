import { TeamView } from "@/components/dashboard";
import { Shell } from "@/components/shell";
import { requireRestaurant } from "@/lib/session";

export default async function Page({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const user = await requireRestaurant(slug, "team", "users.manage");
  return <Shell user={user}><TeamView slug={slug} /></Shell>;
}
