"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ApiError, api, renewSession } from "@/lib/api";
import { errorText } from "@/components/platform/shared";
import { apiRoot } from "@/components/restaurant/shared";

export type Mode = "dine_in" | "takeaway" | "delivery";
export type Choice = { id: string; name: string };
export type Variant = Choice & { available: boolean; price_cents: number; pricing: "replace" | "adjust" };
export type Group = Choice & { minimum: number; maximum: number; modifiers: (Choice & { price_cents: number })[] };
export type Item = Choice & { category_id: string; code: string; description: string; available: boolean;
  featured: boolean; photo_id?: string; image_id?: string; price_cents: number; variants: Variant[]; modifier_groups: Group[] };
export type Catalog = { categories: Choice[]; items: Item[] };
export type OrderLine = { id: string; item_id: string; variant_id: string | null; status: string; quantity: number;
  unit_cents: number; discount_cents: number; notes: string; snapshot: { name: string; variant: string | null;
    modifiers: (Choice & { price_cents: number })[]; area: string } };
export type Account = { id: string; name: string; total_cents: number; discount_cents: number;
  subtotal_cents: number; shipping_cents: number; lines: { line_id: string; quantity: number; discount_cents: number }[] };
export type OrderRecord = { id: string; number: number; mode: Mode; status: string; financial_status: string;
  table_id: string | null; table_number?: string; table_name?: string; waiter_id: string | null;
  waiter_name?: string; guests: number; notes: string; version: number; created_at: number;
  subtotal_cents: number; discount_cents: number; shipping_cents: number; total_cents: number; delivery_state: string | null };
export type Order = OrderRecord & { lines: OrderLine[]; accounts: Account[]; contact: Record<string, string | number | null> };
export type ServiceTable = { id: string; number: string; name?: string; state: string; area: string; capacity: number;
  active: boolean; order_id: string | null; order_number: number | null; total_cents?: number;
  preparation_status?: string; waiter_name?: string; seated_at?: number };
export type PosOptions = { mode_options: Mode[]; customers: Choice[]; waiters: Choice[]; station_staff?: Choice[] };
export type TicketLine = { id: string; state: string; snapshot: OrderLine["snapshot"] &
  { quantity: number; notes: string; before?: { quantity: number; notes: string } } };
export type Ticket = { id: string; number: number; kind: string; state: string; order_version: number; created_at: number;
  current_table?: string; snapshot: { area: string; table: string; order_number: number; mode: Mode; notes: string; waiter: string; reason?: string };
  items: TicketLine[] };
export const captions: Record<string, string> = {
  dine_in: "En mesa", takeaway: "Para llevar", delivery: "A domicilio", draft: "Borrador", confirmed: "Confirmado",
  sent: "Enviado", new: "Nuevo", preparing: "En preparación", ready: "Listo", delivered: "Entregado",
  cancelled: "Cancelado", unpaid: "Pendiente de cobro", bill_requested: "Cuenta solicitada", available: "Disponible",
  occupied: "Ocupada", payment_due: "Cuenta solicitada", reserved: "Reservada", cleaning: "Limpieza",
  out_of_service: "Fuera de servicio", inactive: "Inactiva", initial: "Inicial", additional: "Adicional", adjustment: "Ajuste",
  cancellation: "Cancelación", transfer: "Traslado", pending: "Pendiente", en_route: "En camino",
  created: "Pedido creado", add: "Producto agregado", edit: "Producto modificado", remove: "Producto retirado", create: "Pedido creado",
  send: "Comandas enviadas", details: "Datos actualizados", confirm: "Pedido confirmado", bill: "Cuenta solicitada",
  reopen_bill: "Cuenta reabierta", split: "Cuenta dividida", merge: "Cuentas combinadas", discount: "Descuento",
  cancel: "Pedido cancelado", kitchen_state: "Actualización de cocina", deliver: "Pedido entregado",
};
export const caption = (value: string) => captions[value] ?? value;
export const shortTime = (at: number) => new Intl.DateTimeFormat("es-GT", {
  dateStyle: "short", timeStyle: "short", timeZone: "America/Guatemala",
}).format(at * 1000);
export const tableLabel = (table: Pick<ServiceTable, "name" | "number">) => table.name || (/^mesa\b/i.test(table.number) ? table.number : `Mesa ${table.number}`);
export const uid = () => crypto.randomUUID();

export function PosState({ value }: { value: string }) {
  return <span className="pos-state" data-state={value}>{caption(value)}</span>;
}

const keys: Record<string, string[]> = {
  orders: ["/orders", "/operational-summary"],
  tables: ["/service-tables", "/operational-summary"],
  kitchen: ["/kitchen", "/operational-summary"],
  catalog: ["/catalog", "/pos/options", "/pos/config"],
};
type Feed = keyof typeof keys;

function invalidate(cache: ReturnType<typeof useQueryClient>, slug: string, feeds: Feed[]) {
  const root = apiRoot(slug);
  const paths = feeds.flatMap((feed) => keys[feed]);
  return cache.invalidateQueries({ predicate: ({ queryKey }) =>
    queryKey[0] === "pos" && typeof queryKey[1] === "string" &&
    paths.some((path) => queryKey[1] === root + path || String(queryKey[1]).startsWith(`${root}${path}/`) ||
      String(queryKey[1]).startsWith(`${root}${path}?`)),
  });
}

export function usePosData<T>(path: string, enabled = true) {
  return useQuery({ queryKey: ["pos", path], queryFn: () => api<T>(path), enabled,
    retry: (count, error) => (!(error instanceof ApiError) || error.status >= 500) && count < 2 });
}

export function usePosFeed(slug: string, feeds: string) {
  const cache = useQueryClient();
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    const wanted = feeds.split(",") as Feed[];
    let disposed = false;
    let socket: WebSocket;
    let online = false;
    let timer: ReturnType<typeof setTimeout>;
    let delay = 1000;
    const refresh = (groups = wanted) => void invalidate(cache, slug, groups);
    const connect = () => {
      if (disposed) return;
      const url = new URL(`/api${apiRoot(slug)}/events`, window.location.href);
      url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(url);
      socket.onmessage = ({ data }) => {
        try {
          const frame = JSON.parse(data) as { type: string; events: string[] };
          if (frame.type === "sync") {
            delay = 1000;
            online = true;
            setConnected(true);
            refresh();
          } else if (frame.type === "changed") {
            const groups = new Set<Feed>();
            for (const event of frame.events) {
              if (event.startsWith("order.")) { groups.add("orders"); groups.add("tables"); }
              if (event.startsWith("table.")) { groups.add("tables"); groups.add("orders"); }
              if (event.startsWith("kitchen_ticket.")) {
                groups.add("kitchen"); groups.add("orders"); groups.add("tables");
              }
              if (event.startsWith("menu.") || event.startsWith("pos.settings")) {
                groups.add("catalog"); groups.add("kitchen");
              }
            }
            refresh(wanted.filter((feed) => groups.has(feed)));
          }
        } catch {
          refresh();
        }
      };
      socket.onclose = () => {
        if (disposed) return;
        online = false;
        setConnected(false);
        timer = setTimeout(() => {
          void renewSession().catch(() => undefined).finally(connect);
        }, delay);
        delay = Math.min(30000, delay * 2);
      };
    };
    connect();
    const fallback = setInterval(() => { if (!online) refresh(); }, 5000);
    return () => {
      disposed = true;
      clearTimeout(timer);
      clearInterval(fallback);
      socket?.close();
    };
  }, [cache, feeds, slug]);
  return connected;
}

type Result = { id: string; version: number; tickets?: string[] };

export function usePosWrite(slug: string) {
  const cache = useQueryClient();
  const inFlight = useRef(false);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  const [success, setSuccess] = useState("");
  async function write(path: string, body: object, note?: string): Promise<Result | null> {
    if (inFlight.current) return null;
    inFlight.current = true;
    setPending(true);
    setMessage("");
    setSuccess("");
    try {
      const execute = () => api<Result>(`${apiRoot(slug)}${path}`, { method: "POST", body: JSON.stringify(body) });
      const result = await execute().catch((error: unknown) => {
        if (error instanceof TypeError) return execute();
        throw error;
      });
      await invalidate(cache, slug, ["orders", "tables", "kitchen"]);
      setSuccess(note ?? "Cambios guardados.");
      return result;
    } catch (error) {
      setMessage(errorText(error));
      if (error instanceof ApiError && error.status === 409) await invalidate(cache, slug, ["orders", "tables", "kitchen"]);
      return null;
    } finally {
      inFlight.current = false;
      setPending(false);
    }
  }
  return { write, pending, message, success, clear: () => { setSuccess(""); setMessage(""); } };
}
export type PosWrite = ReturnType<typeof usePosWrite>;

export function LiveIndicator({ connected }: { connected: boolean }) {
  return <span className="pos-live" role="status" data-live={connected}>{connected ? "En vivo" : "Actualización periódica"}</span>;
}

export function FieldRow({ label, children }: { label: string; children: ReactNode }) {
  return <label className="pos-field"><span>{label}</span>{children}</label>;
}
