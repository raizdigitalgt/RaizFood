"use client";

import { Armchair, ClipboardList, Clock3, CookingPot, Maximize2, Plus } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Message } from "@/components/auth";
import { Heading, Load, Modal, Note, Table, queryString } from "@/components/platform/shared";
import { Pager, apiRoot } from "@/components/restaurant/shared";
import { Button } from "@/components/ui/button";
import { money } from "@/lib/api";
import { OrderTools, TicketLines, TicketPreview } from "./documents";
import {
  caption, FieldRow, LiveIndicator, PosState, shortTime, tableLabel, uid, usePosData, usePosFeed, usePosWrite,
  type Choice, type Order, type OrderRecord, type ServiceTable, type Ticket,
} from "./shared";

type Props = { slug: string; permissions: string[] };
const elapsed = (at: number, now: number) => Math.max(0, Math.floor((now - at) / 60));
function useClock() {
  const [clock, setClock] = useState(() => Math.floor(Date.now() / 1000));
  useEffect(() => {
    const timer = setInterval(() => setClock(Math.floor(Date.now() / 1000)), 15000);
    return () => clearInterval(timer);
  }, []);
  return clock;
}

export function Floor({ slug, permissions }: Props) {
  const connected = usePosFeed(slug, "tables,orders");
  const query = usePosData<ServiceTable[]>(`${apiRoot(slug)}/service-tables`);
  const [state, setState] = useState("");
  const [area, setArea] = useState("");
  const clock = useClock();
  const areas = [...new Set(query.data?.map((entry) => entry.area))];
  const visible = query.data?.filter((entry) => (!state || state === entry.state) && (!area || area === entry.area));
  const canCreate = permissions.includes("orders.create");
  return <section className="pos-floor">
    <div className="pos-toolbar"><h2>Operación de mesas</h2><LiveIndicator connected={connected} /></div>
    <div className="pos-controls">
      <FieldRow label="Área del salón"><select value={area} onChange={(event) => setArea(event.target.value)}>
        <option value="">Todas las áreas</option>{areas.map((entry) => <option key={entry}>{entry}</option>)}</select></FieldRow>
      <FieldRow label="Estado de mesa"><select value={state} onChange={(event) => setState(event.target.value)}>
        <option value="">Todos los estados</option>
        {["available", "occupied", "payment_due", "reserved", "cleaning", "out_of_service"].map((entry) =>
          <option value={entry} key={entry}>{caption(entry)}</option>)}</select></FieldRow>
    </div>
    {!visible ? <Load error={query.error} retry={query.refetch} /> : !visible.length ? <p className="pos-empty">No hay mesas en esta vista.</p> :
      <div className="pos-floor-grid">{visible.map((entry) => <article className="panel pos-table" data-state={entry.state} key={entry.id}>
        <div className="pos-toolbar"><Armchair size={20} /><PosState value={entry.state} /></div>
        <h3>{tableLabel(entry)}</h3><p>{entry.area} · {entry.capacity} plazas</p>
        {entry.order_id && <div className="pos-table-order">
          <strong>#{entry.order_number} · {money(entry.total_cents ?? 0)}</strong>
          <small>{entry.waiter_name || "Sin mesero"}{entry.seated_at ? ` · ${elapsed(entry.seated_at, clock)} min` : ""}</small>
          {entry.preparation_status && <PosState value={entry.preparation_status} />}
        </div>}
        {entry.order_id && permissions.includes("orders.view") && <Button asChild variant="outline" className="pos-button-small">
          <Link href={`/app/${slug}/pos?order=${entry.order_id}`}>Abrir pedido</Link></Button>}
        {!entry.order_id && entry.state === "available" && canCreate && <Button asChild className="pos-button-small">
          <Link href={`/app/${slug}/pos?table=${entry.id}`}>Seleccionar mesa</Link></Button>}
      </article>)}</div>}
  </section>;
}

const statuses = ["draft", "confirmed", "sent", "preparing", "ready", "delivered", "cancelled"];
export function OrderList({ slug, permissions }: Props) {
  const root = apiRoot(slug);
  const connected = usePosFeed(slug, "orders,kitchen,tables");
  const [filters, setFilters] = useState({ q: "", status: "", mode: "", table_id: "", user_id: "", after: "", before: "" });
  const [page, setPage] = useState(1);
  const [preview, setPreview] = useState<{ id: string; type: "bill" | "history" | "tickets" } | null>(null);
  const options = usePosData<{ tables: Pick<ServiceTable, "id" | "number" | "name">[]; waiters: Choice[] }>(
    `${root}/orders/filters`);
  const params = { ...filters, page: String(page),
    after: filters.after ? String(Date.parse(`${filters.after}T00:00:00-06:00`) / 1000) : "",
    before: filters.before ? String(Date.parse(`${filters.before}T23:59:59-06:00`) / 1000) : "" };
  const request = usePosData<{ items: OrderRecord[]; total: number }>(`${root}/orders?${queryString(params)}`);
  const detail = usePosData<Order>(`${root}/orders/${preview?.id ?? ""}`, !!preview);
  const set = (key: keyof typeof filters, value: string) => { setFilters({ ...filters, [key]: value }); setPage(1); };
  const staff = options.data?.waiters ?? [];
  return <>
    <Heading title="Pedidos" text="Consulta pedidos abiertos y el historial del servicio." action={<div className="pos-actions">
      <LiveIndicator connected={connected} />{permissions.includes("orders.create") && <Button asChild>
        <Link href={`/app/${slug}/pos?new=1`}><Plus size={17} /> Nuevo pedido</Link></Button>}
    </div>} />
    <div className="panel pos-controls">
      <FieldRow label="Buscar pedido"><input type="search" value={filters.q} maxLength={100}
        onChange={(event) => set("q", event.target.value)} placeholder="Número, cliente u observaciones" /></FieldRow>
      <FieldRow label="Estado"><select value={filters.status} onChange={(event) => set("status", event.target.value)}>
        <option value="">Todos</option>{statuses.map((entry) => <option key={entry} value={entry}>{caption(entry)}</option>)}</select></FieldRow>
      <FieldRow label="Modalidad"><select value={filters.mode} onChange={(event) => set("mode", event.target.value)}>
        <option value="">Todas</option>{["dine_in", "takeaway", "delivery"].map((entry) =>
          <option key={entry} value={entry}>{caption(entry)}</option>)}</select></FieldRow>
      {options.data && <FieldRow label="Mesa"><select value={filters.table_id} onChange={(event) => set("table_id", event.target.value)}>
        <option value="">Todas</option>{options.data.tables.map((entry) => <option key={entry.id} value={entry.id}>{tableLabel(entry)}</option>)}</select></FieldRow>}
      {(staff.length > 0 || filters.user_id) && <FieldRow label="Mesero"><select value={filters.user_id} onChange={(event) => set("user_id", event.target.value)}>
        <option value="">Todos</option>{staff.map(({ id, name }) => <option key={id} value={id}>{name}</option>)}</select></FieldRow>}
      <FieldRow label="Desde"><input type="date" value={filters.after} onChange={(event) => set("after", event.target.value)} /></FieldRow>
      <FieldRow label="Hasta"><input type="date" value={filters.before} onChange={(event) => set("before", event.target.value)} /></FieldRow>
    </div>
    {request.data ? <><Table rows={request.data.items} rowKey={(entry) => entry.id} columns={[
      { label: "Pedido", cell: (entry) => <b>#{entry.number}</b> },
      { label: "Fecha", cell: (entry) => shortTime(entry.created_at) },
      { label: "Modalidad", cell: (entry) => entry.table_number ? `Mesa ${entry.table_number}` : caption(entry.mode) },
      { label: "Mesero", cell: (entry) => entry.waiter_name || "—" },
      { label: "Cocina", cell: (entry) => <PosState value={entry.status} /> },
      { label: "Cuenta", cell: (entry) => <><PosState value={entry.financial_status} /><br />{money(entry.total_cents)}</> },
      { label: "Acciones", cell: (entry) => <div className="pos-actions">
        <Button asChild className="pos-button-small" variant="outline"><Link href={`/app/${slug}/pos?order=${entry.id}`}>Abrir #{entry.number}</Link></Button>
        <Button className="pos-button-small" variant="ghost" onClick={() => setPreview({ id: entry.id, type: "history" })}>Actividad</Button>
        <Button className="pos-button-small" variant="ghost" onClick={() => setPreview({ id: entry.id, type: "tickets" })}>Comandas</Button>
        {permissions.includes("receipts.preview") && <Button className="pos-button-small" variant="ghost"
          onClick={() => setPreview({ id: entry.id, type: "bill" })}>Ver cuenta</Button>}
      </div> },
    ]} /><Pager page={page} size={20} total={request.data.total} setPage={setPage} /></> : <Load error={request.error} retry={request.refetch} />}
    {preview && (detail.data ? <OrderTools slug={slug} order={detail.data} tool={preview}
      permissions={permissions} close={() => setPreview(null)} /> : <Modal title="Pedido" close={() => setPreview(null)}>
        <Load error={detail.error} retry={detail.refetch} /></Modal>)}
  </>;
}

type KitchenData = { restaurant: string; tickets: Ticket[]; areas: (Choice & { active: boolean })[];
  general: boolean; warning_minutes: number };
const kds = [{ key: "new", name: "Nuevas" }, { key: "preparing", name: "En preparación" }, { key: "ready", name: "Listas" }];
export function Kitchen({ slug, permissions }: Props) {
  const connected = usePosFeed(slug, "kitchen,orders,catalog");
  const [area, setArea] = useState("");
  const [selected, setSelected] = useState("");
  const [full, setFull] = useState(false);
  const clock = useClock();
  const request = usePosData<KitchenData>(`${apiRoot(slug)}/kitchen?${queryString({ area })}`);
  const action = usePosWrite(slug);
  const canUpdate = permissions.includes("kitchen.update");
  const update = (ticket: Ticket, state: string, ticketLine?: string) => void action.write(
    `/kitchen/tickets/${ticket.id}/state`, { state, ticket_line_id: ticketLine, version: ticket.order_version, request_id: uid() });
  return <div className={`pos-kds ${full ? "pos-kds-full" : ""}`}>
    <div className="pos-toolbar"><div><h1>Pantalla de cocina</h1>
      {request.data && <p className="pos-context">{request.data.restaurant}</p>}</div>
      <time suppressHydrationWarning className="pos-context">{shortTime(clock)}</time>
      <LiveIndicator connected={connected} />
      <Button variant="outline" onClick={() => setFull(!full)}><Maximize2 size={16} />
        {full ? "Salir de pantalla completa" : "Pantalla completa"}</Button>
    </div>
    {action.message && <Message>{action.message}</Message>}
    <Note>{action.success}</Note>
    {!request.data ? <Load error={request.error} retry={request.refetch} /> : <>
      <div className="pos-kds-filter"><FieldRow label="Estación"><select value={area} onChange={(event) => setArea(event.target.value)}>
        <option value="">Todas mis estaciones</option>{request.data.general && <option value="general">General</option>}
        {request.data.areas.map((entry) => <option key={entry.id} value={entry.id}>{entry.name}{entry.active ? "" : " (inactiva)"}</option>)}
      </select></FieldRow></div>
      {!request.data.general && !request.data.areas.length && <p className="pos-empty">Tu usuario no tiene estaciones asignadas.</p>}
      <div className="pos-kds-board">{kds.map((column) => {
        const cards = request.data.tickets.filter((ticket) => ticket.state === column.key);
        return <section key={column.key} aria-label={column.name} className="pos-kds-column">
          <div className="pos-toolbar"><h2>{column.name}</h2><b>{cards.length}</b></div>
          {!cards.length && <p className="pos-empty">Sin comandas</p>}
          {cards.map((ticket) => {
            const time = elapsed(ticket.created_at, clock);
            const late = ticket.state !== "ready" && time >= request.data.warning_minutes;
            return <article key={ticket.id} className="pos-ticket" data-late={late}>
              <div className="pos-toolbar"><h3>Comanda #{ticket.number}</h3><PosState value={ticket.kind} /></div>
              <p className="pos-context">Pedido #{ticket.snapshot.order_number} · {ticket.snapshot.area}</p>
              <p className="pos-context">{ticket.current_table || ticket.snapshot.table || caption(ticket.snapshot.mode)}</p>
              {ticket.snapshot.waiter && <p className="pos-context">{ticket.snapshot.waiter}</p>}
              <time className="pos-context">{shortTime(ticket.created_at)}</time><br />
              <span className="pos-age"><Clock3 size={14} />{time} min{late ? " · Demorada" : ""}</span>
              {ticket.snapshot.notes && <p>{ticket.snapshot.notes}</p>}
              {ticket.snapshot.reason && <p>{ticket.snapshot.reason}</p>}
              <TicketLines ticket={ticket} mark={canUpdate && !action.pending && ticket.state === "preparing"
                ? (line) => update(ticket, "ready", line.id) : undefined} />
              <div className="pos-actions">
                {canUpdate && ticket.state === "new" && <Button className="pos-button-small" disabled={action.pending}
                  onClick={() => update(ticket, "preparing")}>Iniciar preparación</Button>}
                {canUpdate && ticket.state === "preparing" && <Button className="pos-button-small" disabled={action.pending}
                  onClick={() => update(ticket, "ready")}>Marcar todo listo</Button>}
                <Button className="pos-button-small" variant="ghost" onClick={() => setSelected(ticket.id)}>Ver comanda</Button>
              </div>
            </article>;
          })}
        </section>;
      })}</div>
    </>}
    {selected && <Modal title="Vista previa de comanda" close={() => setSelected("")}><TicketPreview slug={slug} id={selected} /></Modal>}
  </div>;
}

type Metrics = { today: number; active: number; states: Record<string, number>; tables: Record<string, number>;
  average_seconds: number | null; stations: { name: string; tickets: number }[]; popular: { name: string; quantity: number }[] };
export function OperationalMetrics({ slug }: { slug: string }) {
  const connected = usePosFeed(slug, "orders,tables,kitchen");
  const query = usePosData<Metrics>(`${apiRoot(slug)}/operational-summary`);
  const data = query.data;
  return <section className="panel commercial-inset commercial-stack">
    <div className="pos-toolbar"><h2>Indicadores de operación</h2><LiveIndicator connected={connected} /></div>
    {data ? <>
      <div className="pos-metrics">
        <article><ClipboardList size={19} /><span>Pedidos hoy</span><strong>{data.today}</strong></article>
        <article><ClipboardList size={19} /><span>Pedidos abiertos</span><strong>{data.active}</strong></article>
        <article><Armchair size={19} /><span>Mesas ocupadas / disponibles</span><strong>
          {(data.tables.occupied ?? 0) + (data.tables.payment_due ?? 0)} / {data.tables.available ?? 0}</strong></article>
        <article><CookingPot size={19} /><span>Preparación promedio</span><strong>{data.average_seconds === null ? "—" :
          `${Math.round(data.average_seconds / 60)} min`}</strong></article>
      </div>
      <div className="pos-metrics-detail">
        <div><h3>Pedidos por estado</h3><ul>{Object.entries(data.states).map(([name, count]) =>
          <li key={name}>{caption(name)} <b>{count}</b></li>)}</ul></div>
        <div><h3>Comandas por estación</h3><ul>{data.stations.map((entry) => <li key={entry.name}>{entry.name} <b>{entry.tickets}</b></li>)}</ul></div>
        <div><h3>Platillos más solicitados</h3><ul>{data.popular.map((entry) => <li key={entry.name}>{entry.name} <b>{entry.quantity}</b></li>)}</ul></div>
      </div>
    </> : <Load error={query.error} retry={query.refetch} />}
  </section>;
}
