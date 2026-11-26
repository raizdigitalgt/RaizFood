import { Overview } from "@/components/platform/overview";
import { Shell } from "@/components/shell";
import { requirePlatform } from "@/lib/session";

export default async function Page() {
  const user = await requirePlatform("/platform/dashboard");
  return <Shell user={user}><Overview scopes={user.platform_permissions} /></Shell>;
}
