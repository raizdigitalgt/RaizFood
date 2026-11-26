import { StaffView } from "@/components/restaurant/staff";
import { Shell } from "@/components/shell";
import { requireRestaurant } from "@/lib/session";

export default async function Page({ params, searchParams }: {
  params: Promise<{ slug: string }>; searchParams: Promise<{ invite?: string }>;
}) {
  const { slug } = await params;
  const query = await searchParams;
  const user = await requireRestaurant(slug, "team", ["users.manage", "users.invite", "roles.manage"]);
  return <Shell user={user}><StaffView slug={slug} permissions={user.permissions} inviteFirst={query.invite === "1"} /></Shell>;
}
