import { redirect } from "next/navigation";
import { TenantPicker } from "@/components/auth";
import { home } from "@/lib/api";
import { requireIdentity } from "@/lib/session";

export default async function Restaurants() {
  const user = await requireIdentity("/restaurantes");
  if (user.platform_admin) redirect(home(user));
  return <TenantPicker user={user} />;
}
