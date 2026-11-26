export interface Tenant { slug: string; name: string }
export interface Identity {
  name: string;
  email: string;
  platform_admin: boolean;
  platform_permissions: string[];
  tenant: Tenant | null;
  restaurants: Tenant[];
  permissions: string[];
}
export interface Plan {
  code: string;
  name: string;
  monthly_cents: number;
  max_admins: number;
  max_staff: number;
  max_total: number;
  fel_enabled: boolean;
}
export interface Restaurant extends Tenant {
  active: boolean;
  created_at: number;
  plan: Plan;
  usage: { admins: number; staff: number; total: number };
}
export interface PlatformDashboard {
  restaurants: number;
  active: number;
  users: number;
  plans: number;
  recent: Restaurant[];
}
export interface RestaurantPage { items: Restaurant[]; total: number }
export interface Member { name: string; email: string; role: string; active: boolean }
export interface Role { code: string; name: string }
export interface Team { items: Member[]; roles: Role[] }

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

async function read<T>(response: Response): Promise<T> {
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const fallback = response.status === 422
      ? "Revisa los campos del formulario."
      : "No se pudo completar la solicitud.";
    throw new ApiError(typeof data?.detail === "string" ? data.detail : fallback, response.status);
  }
  return data as T;
}

let renewing: Promise<Identity> | undefined;

export function renewSession(): Promise<Identity> {
  if (!renewing) {
    const refresh = async () => {
      const current = await fetch("/api/auth/me", { cache: "no-store" });
      if (current.ok) return read<Identity>(current);
      return read<Identity>(await fetch("/api/auth/refresh", { method: "POST" }));
    };
    renewing = (async () => navigator.locks
      ? await navigator.locks.request("raiz-food-refresh", refresh)
      : await refresh())().finally(() => { renewing = undefined; });
  }
  return renewing;
}

export async function api<T>(path: string, init?: RequestInit, retry = true): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body) headers.set("Content-Type", "application/json");
  const execute = () => fetch(`/api${path}`, { ...init, headers, cache: "no-store" });
  const response = await execute();
  if (response.status === 401 && retry) {
    await renewSession();
    return read<T>(await execute());
  }
  return read<T>(response);
}

export function home(identity: Identity) {
  if (identity.platform_admin) return "/platform/dashboard";
  if (identity.tenant) return `/app/${identity.tenant.slug}/dashboard`;
  return "/restaurantes";
}

export const money = (cents: number) => new Intl.NumberFormat("es-GT", {
  style: "currency", currency: "GTQ",
}).format(cents / 100);

export const date = (timestamp: number) => new Intl.DateTimeFormat("es-GT", {
  timeZone: "America/Guatemala", day: "2-digit", month: "2-digit", year: "numeric",
}).format(timestamp * 1000);
