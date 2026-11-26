import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";

import { home, type Identity } from "@/lib/api";

export async function identity() {
  const jar = await cookies();
  const access = jar.get("rf_access");
  if (!access) return null;
  const backend = process.env.RAIZ_BACKEND_URL ?? "http://127.0.0.1:8000";
  const response = await fetch(`${backend}/api/auth/me`, {
    headers: { Cookie: `${access.name}=${access.value}` },
    cache: "no-store",
  });
  if (response.status === 401) return null;
  if (!response.ok) throw new Error("El servicio de sesión no está disponible.");
  return await response.json() as Identity;
}

export async function requireIdentity(destination: string) {
  const user = await identity();
  if (!user) redirect(`/session?next=${encodeURIComponent(destination)}`);
  return user;
}

export async function requirePlatform(destination: string, permission = "dashboard") {
  const user = await requireIdentity(destination);
  if (!user.platform_admin) redirect(home(user));
  if (!user.platform_permissions.includes(permission)) notFound();
  return user;
}

export async function requireRestaurant(slug: string, section: string, permission: string | string[], search = "") {
  const user = await requireIdentity(`/app/${slug}/${section}${search}`);
  if (user.platform_admin) redirect(home(user));
  if (!user.tenant) redirect("/restaurantes");
  const scopes = Array.isArray(permission) ? permission : [permission];
  if (user.tenant.slug !== slug || !scopes.some((scope) => user.permissions.includes(scope))) notFound();
  return user;
}
