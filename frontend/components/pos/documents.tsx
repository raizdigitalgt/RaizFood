"use client";

import { useState, type FormEvent } from "react";
import { Message } from "@/components/auth";
import { Load, Modal } from "@/components/platform/shared";
import { Photo, apiRoot, toCents } from "@/components/restaurant/shared";
import { Button } from "@/components/ui/button";
import { money } from "@/lib/api";
import {
  caption, FieldRow, PosState, shortTime, tableLabel, usePosData,
  type Account, type Order, type OrderLine, type PosOptions, type ServiceTable, type Ticket,
} from "./shared";

export type OrderTool = { type: "bill" | "history" | "tickets" | "details" | "transfer" | "split" | "merge" | "discount" | "remove" | "cancel"; line?: OrderLine };
type Bill = { restaurant: string; logo_id: string | null; order: Order; disclaimer: string };
type Change = { id: string; action: string; actor_id: string; actor_name?: string; created_at: number;
  changes: { reason?: string; status?: string | { before: string; after: string }; financial_status?: { before: string; after: string } } };
const titles: Record<OrderTool["type"], string> = {
  bill: "Cuenta preliminar", history: "Historial del pedido", tickets: "Comandas del pedido", details: "Datos del pedido",
  transfer: "Trasladar mesa", split: "Dividir cuenta", merge: "Combinar cuentas", discount: "Aplicar descuento",
  remove: "Retirar producto", cancel: "Cancelar pedido",
};

function Totals({ entry }: { entry: Pick<Order, "subtotal_cents" | "discount_cents" | "total_cents" | "shipping_cents"> }) {
  return <dl className="pos-receipt-totals">
    <div><dt>Subtotal</dt><dd>{money(entry.subtotal_cents)}</dd></div>
    {entry.discount_cents > 0 && <div><dt>Descuentos</dt><dd>−{money(entry.discount_cents)}</dd></div>}
    {entry.shipping_cents > 0 && <div><dt>Envío</dt><dd>{money(entry.shipping_cents)}</dd></div>}
    <div><dt>Total</dt><dd>{money(entry.total_cents)}</dd></div>
  </dl>;
}

function BillView({ slug, id }: { slug: string; id: string }) {
  const request = usePosData<Bill>(`${apiRoot(slug)}/orders/${id}/bill`);
  const [selected, setSelected] = useState("");
  if (!request.data) return <Load error={request.error} retry={request.refetch} />;
  const { order, restaurant, logo_id, disclaimer } = request.data;
  const account = order.accounts.find((part) => part.id === selected);
  const parts = new Map(account?.lines.map((entry) => [entry.line_id, entry.quantity]));
  const items = order.lines.filter((line) => line.status !== "cancelled" && (!account || parts.has(line.id)));
  return <div className="pos-form">
    {order.accounts.length > 1 && <FieldRow label="Cuenta"><select value={selected} onChange={(event) => setSelected(event.target.value)}>
      <option value="">Pedido completo</option>
      {order.accounts.map((part) => <option key={part.id} value={part.id}>{part.name} · {money(part.total_cents)}</option>)}
    </select></FieldRow>}
    <article className="pos-receipt" aria-label="Vista previa de 80 milímetros">
      {logo_id && <Photo slug={slug} id={logo_id} alt="" />}
      <header><h3>{restaurant}</h3><p>Cuenta preliminar · Pedido #{order.number}</p>
        <p>{order.table_name || caption(order.mode)} · {shortTime(order.created_at)}</p>
        {order.contact.name && <p>Cliente · {order.contact.name}</p>}
        {order.waiter_name && <p>Mesero · {order.waiter_name}</p>}
        {account && <p>{account.name}</p>}</header>
      <ul>{items.map((line) => {
        const quantity = parts.get(line.id) ?? line.quantity;
        return <li key={line.id}><div><span>{quantity} × {line.snapshot.name}</span><span>{money(line.unit_cents * quantity)}</span></div>
          <small>Precio unitario {money(line.unit_cents)}</small>
          {line.snapshot.variant && <small>{line.snapshot.variant}</small>}
          {line.snapshot.modifiers.length > 0 && <small>{line.snapshot.modifiers.map((extra) => extra.name).join(", ")}</small>}
          {line.notes && <small>{line.notes}</small>}
        </li>;
      })}</ul>
      <Totals entry={account ?? order} /><p className="pos-receipt-warning">{disclaimer}</p>
    </article>
  </div>;
}

function History({ slug, id }: { slug: string; id: string }) {
  const query = usePosData<Change[]>(`${apiRoot(slug)}/orders/${id}/history`);
  if (!query.data) return <Load error={query.error} retry={query.refetch} />;
  return <ol className="pos-history">{query.data.map((entry) => {
    const state = entry.changes.status ?? entry.changes.financial_status;
    return <li key={entry.id}><div><strong>{caption(entry.action)}</strong><time>{shortTime(entry.created_at)}</time></div>
      {entry.actor_name && <small>{entry.actor_name}</small>}
      {typeof state === "string" ? <p>{caption(state)}</p> : state && <p>{caption(state.before)} → {caption(state.after)}</p>}
      {entry.changes.reason && <p>{entry.changes.reason}</p>}</li>;
  })}</ol>;
}

export function TicketPreview({ slug, id }: { slug: string; id: string }) {
  const query = usePosData<Ticket>(`${apiRoot(slug)}/kitchen/tickets/${id}`);
  if (!query.data) return <Load error={query.error} retry={query.refetch} />;
  const ticket = query.data;
  return <article className="pos-receipt" aria-label="Vista previa de comanda de 80 milímetros">
    <header><h3>{ticket.snapshot.area} · #{ticket.number}</h3><p>{caption(ticket.kind)} · Pedido #{ticket.snapshot.order_number}</p>
      <p>{ticket.snapshot.table || caption(ticket.snapshot.mode)} · {shortTime(ticket.created_at)}</p>
      {ticket.snapshot.waiter && <p>Mesero · {ticket.snapshot.waiter}</p>}
      {ticket.snapshot.notes && <p>{ticket.snapshot.notes}</p>}
      {ticket.snapshot.reason && <p>{ticket.snapshot.reason}</p>}</header>
    <ul>{ticket.items.map((line) => <li key={line.id}>
      <b>{line.snapshot.quantity} × {line.snapshot.name}</b>
      {line.snapshot.variant && <small>{line.snapshot.variant}</small>}
      {line.snapshot.modifiers.length > 0 && <small>{line.snapshot.modifiers.map((extra) => extra.name).join(", ")}</small>}
      {line.snapshot.notes && <small>{line.snapshot.notes}</small>}
      {line.snapshot.before && <small>Antes · {line.snapshot.before.quantity} unidad(es) {line.snapshot.before.notes}</small>}
    </li>)}</ul>
  </article>;
}

function Tickets({ slug, id }: { slug: string; id: string }) {
  const query = usePosData<Ticket[]>(`${apiRoot(slug)}/orders/${id}/tickets`);
  const [selected, setSelected] = useState("");
  if (!query.data) return <Load error={query.error} retry={query.refetch} />;
  if (!query.data.length) return <p className="pos-empty">Aún no hay comandas.</p>;
  return <div className="pos-form"><FieldRow label="Comanda"><select value={selected || query.data[0].id}
    onChange={(event) => setSelected(event.target.value)}>
    {query.data.map((ticket) => <option key={ticket.id} value={ticket.id}>
      #{ticket.number} · {ticket.snapshot.area} · {caption(ticket.kind)} · {caption(ticket.state)}
    </option>)}</select></FieldRow>
    <TicketPreview slug={slug} id={selected || query.data[0].id} />
  </div>;
}

export function OrderTools({ slug, order, tool, permissions, pending = false, message, close, save }: {
  slug: string; order: Order; tool: OrderTool; permissions: string[];
  message?: string; pending?: boolean; close: () => void; save?: (op: string, body: object) => Promise<void>;
}) {
  const { type, line } = tool;
  const root = apiRoot(slug);
  const assign = permissions.includes("orders.assign");
  const tables = usePosData<ServiceTable[]>(`${root}/service-tables`, type === "transfer");
  const staff = usePosData<PosOptions>(`${root}/pos/options?customer=`, type === "details" && assign);
  const [source, setSource] = useState(order.accounts[0]?.id ?? "");
  const [kind, setKind] = useState("fixed");
  const portion: Account | undefined = order.accounts.find((entry) => entry.id === source);
  const active = order.lines.filter((item) => item.status !== "cancelled");
  const available = tables.data?.filter((entry) => entry.state === "available" && !entry.order_id) ?? [];
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const get = (key: string) => String(data.get(key) ?? "").trim();
    const reason = get("reason");
    const payloads: Partial<Record<OrderTool["type"], object>> = {
      details: { notes: get("notes"), waiter_id: assign ? get("waiter") || order.waiter_id : order.waiter_id },
      transfer: { table_id: get("table"), reason },
      discount: { kind, value: toCents(get("amount")), line_id: line?.id, reason },
      remove: { line_id: line?.id, reason }, cancel: { reason }, merge: {},
      split: { name: get("name"), source_id: source, items: (portion?.lines ?? []).map((entry) => ({
        line_id: entry.line_id, quantity: Number(get(entry.line_id)),
      })).filter((entry) => entry.quantity > 0) },
    };
    if (save) void save(type, payloads[type] ?? {});
  };
  return <Modal title={titles[type]} close={close}>
    {type === "bill" ? <BillView slug={slug} id={order.id} /> :
      type === "history" ? <History slug={slug} id={order.id} /> :
      type === "tickets" ? <Tickets slug={slug} id={order.id} /> :
      <form className="pos-form" onSubmit={submit}>
        {message && <Message>{message}</Message>}
        {line && <p>{line.snapshot.name} · {line.quantity} × {money(line.unit_cents)}</p>}
        {type === "details" && <>
          {assign && <FieldRow label="Mesero"><select name="waiter" defaultValue={order.waiter_id ?? ""}>
            {order.waiter_id && !staff.data?.waiters.some((entry) => entry.id === order.waiter_id) &&
              <option value={order.waiter_id}>{order.waiter_name || "Mesero actual"}</option>}
            {staff.data?.waiters.map((entry) => <option key={entry.id} value={entry.id}>{entry.name}</option>)}
          </select></FieldRow>}
          <FieldRow label="Observaciones del pedido"><textarea name="notes" defaultValue={order.notes} maxLength={1000} /></FieldRow>
        </>}
        {type === "transfer" && <FieldRow label="Mesa de destino"><select required name="table"><option value="">Seleccionar mesa</option>
          {available.map((entry) => <option key={entry.id} value={entry.id}>{tableLabel(entry)} · {entry.area}</option>)}
        </select></FieldRow>}
        {type === "split" && <>
          <FieldRow label="Cuenta de origen"><select value={source} onChange={(event) => setSource(event.target.value)}>
            {order.accounts.map((entry) => <option key={entry.id} value={entry.id}>{entry.name} · {money(entry.total_cents)}</option>)}
          </select></FieldRow>
          <FieldRow label="Nombre de la nueva cuenta"><input name="name" required maxLength={100}
            defaultValue={`Cuenta ${order.accounts.length + 1}`} /></FieldRow>
          <fieldset className="restaurant-fieldset" key={source}><legend>Cantidades para mover</legend>
            {portion?.lines.map((entry) => {
              const product = active.find((item) => item.id === entry.line_id);
              return <FieldRow key={entry.line_id} label={`${product?.snapshot.name ?? "Producto"} (${entry.quantity} en cuenta)`}>
                <input name={entry.line_id} type="number" min="0" max={entry.quantity} defaultValue="0" required />
              </FieldRow>;
            })}
          </fieldset>
        </>}
        {type === "merge" && <p>Las {order.accounts.length} cuentas volverán a la cuenta principal. Total {money(order.total_cents)}.</p>}
        {type === "discount" && <div className="pos-form-grid">
          <FieldRow label="Tipo de descuento"><select value={kind} onChange={(event) => setKind(event.target.value)}>
            <option value="fixed">Monto fijo</option><option value="percent">Porcentaje</option>
          </select></FieldRow>
          <FieldRow label={kind === "fixed" ? "Monto (Q)" : "Porcentaje (%)"}><input name="amount" required type="number"
            min="0" max={kind === "fixed" ? 1_000_000 : 100} step="0.01" /></FieldRow>
        </div>}
        {["transfer", "discount", "remove", "cancel"].includes(type) && <FieldRow label="Motivo">
          <textarea name="reason" minLength={type === "transfer" ? undefined : 3} maxLength={1000} required={type !== "transfer"} />
        </FieldRow>}
        {type === "cancel" && <p>El pedido se cancelará y la mesa quedará disponible.</p>}
        {type === "remove" && <p>Se enviará una comanda de cancelación a la estación correspondiente.</p>}
        <div className="pos-actions"><Button type="button" variant="outline" onClick={close}>Volver</Button>
          <Button type="submit" disabled={pending || (type === "transfer" && !available.length)}>
            {type === "details" ? "Guardar cambios" : titles[type]}</Button></div>
      </form>}
  </Modal>;
}

export function TicketLines({ ticket, mark }: { ticket: Ticket; mark?: (line: Ticket["items"][number]) => void }) {
  return <ul className="pos-ticket-lines">{ticket.items.map((line) => <li key={line.id} data-state={line.state}>
    <div><b>{line.snapshot.quantity} × {line.snapshot.name}</b>
      <small>{[line.snapshot.variant, ...line.snapshot.modifiers.map((extra) => extra.name)].filter(Boolean).join(" · ")}</small>
      {line.snapshot.notes && <p>{line.snapshot.notes}</p>}
      {line.snapshot.before && <small>Antes · {line.snapshot.before.quantity} unidad(es) {line.snapshot.before.notes}</small>}
    </div>
    {mark && !["ready", "cancelled"].includes(line.state)
      ? <Button className="pos-button-small" variant="outline" onClick={() => mark(line)}>Listo</Button> : <PosState value={line.state} />}
  </li>)}</ul>;
}
