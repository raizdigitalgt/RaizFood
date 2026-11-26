"use client";

import { ArrowRight, ClipboardList, Grid2X2, List, Search, ShoppingBasket } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { Message } from "@/components/auth";
import { Load, Modal, Note } from "@/components/platform/shared";
import { Photo, apiRoot, toCents } from "@/components/restaurant/shared";
import { Button } from "@/components/ui/button";
import { money } from "@/lib/api";
import { OrderTools, type OrderTool } from "./documents";
import {
  caption, FieldRow, LiveIndicator, PosState, shortTime, tableLabel, uid, usePosData, usePosFeed, usePosWrite,
  type Catalog, type Item, type Mode, type Order, type OrderLine, type OrderRecord, type PosOptions,
  type PosWrite, type ServiceTable,
} from "./shared";

type Props = { slug: string; permissions: string[]; selected?: string; table?: string; initialOpen?: boolean };
type Page = { items: OrderRecord[]; total: number };
const normalize = (value: string) => value.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();

export function Workspace({ slug, permissions, selected, table, initialOpen }: Props) {
  const root = apiRoot(slug);
  const router = useRouter();
  const connected = usePosFeed(slug, "orders,tables,catalog,kitchen");
  const transactions = usePosWrite(slug);
  const [start, setStart] = useState(!!initialOpen);
  const [cart, setCart] = useState(false);
  const [tool, setTool] = useState<OrderTool | null>(null);
  const [editing, setEditing] = useState<{ item: Item; line?: OrderLine } | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("");
  const [category, setCategory] = useState("all");
  const [compact, setCompact] = useState(false);
  const create = permissions.includes("orders.create");
  const catalog = usePosData<Catalog>(`${root}/catalog`);
  const active = usePosData<Page>(`${root}/orders?active=true&size=100`);
  const current = usePosData<Order>(`${root}/orders/${encodeURIComponent(selected ?? "")}`, !!selected);
  const order = selected ? current.data : undefined;
  const editable = !!order && order.financial_status === "unpaid" && order.status !== "cancelled" && (order.status !== "delivered" || order.mode === "dine_in")
    && order.accounts.length <= 1 && permissions.includes("orders.update");
  const mutable = !!order && order.status !== "cancelled";
  const can = (scope: string) => permissions.includes(scope);
  const menu = catalog.data;
  useEffect(() => {
    const pending = setTimeout(() => setFilter(normalize(search.trim())), 180);
    return () => clearTimeout(pending);
  }, [search]);
  const items = menu?.items.filter((item) => (category === "all" || (category === "featured" ? item.featured : category === item.category_id))
    && normalize([item.name, item.code, item.description].join(" ")).includes(filter));
  const navigate = (id?: string) => {
    setCart(false);
    setTool(null);
    setEditing(null);
    transactions.clear();
    router.push(`/app/${slug}/pos${id ? `?order=${id}` : ""}`);
  };
  const run = (op: string, extra?: object, note?: string) => order
    ? transactions.write(`/orders/${order.id}/actions`, { op, request_id: uid(), version: order.version, ...extra }, note)
    : Promise.resolve(null);
  const add = (item: Item) => {
    if (!editable) return;
    if (item.variants.some((entry) => entry.available) || item.modifier_groups.some((group) => group.minimum > 0)) {
      setEditing({ item });
    }
    else void run("add", { item_id: item.id, quantity: 1 }, "Producto agregado.");
  };
  const liveLines = order?.lines.filter((line) => line.status !== "cancelled") ?? [];
  const ticketsPending = liveLines.some((line) => line.status === "new");
  const showStart = create && (start || (!!table && !selected));
  return <div className="pos-shell">
    <div className="pos-toolbar">
      <h1>Punto de venta</h1><LiveIndicator connected={connected} />
      <div className="pos-actions">
        <Button asChild variant="outline"><Link href={`/app/${slug}/tables`}>Mesas</Link></Button>
        {create && <Button onClick={() => { transactions.clear(); setStart(true); }}>Nuevo pedido</Button>}
      </div>
    </div>
    <div className="pos-order-switch">
      <FieldRow label="Pedidos abiertos"><select value={selected ?? ""} onChange={(event) => navigate(event.target.value)}>
        <option value="">Seleccionar un pedido</option>
        {!!selected && !active.data?.items.some((entry) => entry.id === selected) &&
          <option value={selected}>{order ? `#${order.number} · ${caption(order.status)}` : "Pedido seleccionado"}</option>}
        {active.data?.items.map((entry) => <option value={entry.id} key={entry.id}>
          #{entry.number} · {entry.table_number ? `Mesa ${entry.table_number}` : caption(entry.mode)} · {caption(entry.status)}
        </option>)}
      </select></FieldRow>
      <Button asChild variant="ghost"><Link href={`/app/${slug}/orders`}><ClipboardList size={16} /> Historial</Link></Button>
    </div>
    {current.error && selected && <Load error={current.error} retry={current.refetch} />}
    {!!transactions.message && <Message>{transactions.message}</Message>}
    <Note>{transactions.success}</Note>
    <div className="pos-columns">
      <section className="pos-catalog" aria-label="Catálogo del POS">
        <div className="pos-toolbar">
          <label className="pos-search"><Search size={17} /><input aria-label="Buscar productos" placeholder="Buscar producto o código"
            value={search} onChange={(event) => setSearch(event.target.value)} /></label>
          <Button className="pos-button-icon" variant="outline" aria-label={compact ? "Mostrar cuadrícula" : "Mostrar vista compacta"}
            onClick={() => setCompact(!compact)}>{compact ? <Grid2X2 size={17} /> : <List size={17} />}</Button>
        </div>
        <div className="pos-filters" aria-label="Categorías">
          {[{ id: "all", name: "Todos" }, { id: "featured", name: "Destacados" }, ...(menu?.categories ?? [])].map((entry) =>
            <button key={entry.id} type="button" className="pos-chip" aria-pressed={category === entry.id}
              onClick={() => setCategory(entry.id)}>{entry.name}</button>)}
        </div>
        {!items ? <Load error={catalog.error} retry={catalog.refetch} /> : !items.length ?
          <p className="pos-empty">No se encontraron productos.</p> : <div className="pos-products" data-compact={compact}>
            {items.map((item) => <div key={item.id} className="pos-product-cell"><button type="button" className="pos-product"
              disabled={!editable || !item.available || transactions.pending} onClick={() => add(item)}>
              {!compact && <Photo slug={slug} id={item.image_id} alt="" />}
              <span><strong>{item.name}{item.featured && <span className="pos-featured" aria-label="Destacado">★</span>}</strong>
                {!item.available ? <small>No disponible</small> : <small>{item.code}{item.variants.length ? " · Variantes" : ""}</small>}</span>
              <b>{money(item.price_cents)}</b>
            </button>{item.modifier_groups.some((group) => group.modifiers.length) &&
              !item.variants.some((entry) => entry.available) &&
              item.modifier_groups.every((group) => group.minimum === 0) &&
              <button type="button" className="pos-chip pos-customize" disabled={!editable || !item.available || transactions.pending}
                onClick={() => setEditing({ item })} aria-label={`Personalizar ${item.name}`}>Personalizar</button>}
            </div>)}
          </div>}
      </section>
      <aside className={`pos-cart ${cart ? "pos-cart-open" : ""}`} aria-label="Carrito del pedido">
        <div className="pos-toolbar"><h2>{order ? `Pedido #${order.number}` : "Pedido"}</h2>
          {order && <PosState value={order.status} />}
          <button className="pos-cart-close pos-chip" type="button" onClick={() => setCart(false)}>Cerrar</button></div>
        {order ? <>
          <p className="pos-context">{order.table_name || caption(order.mode)}
            {order.guests > 0 && ` · ${order.guests} comensales`}{order.waiter_name && ` · ${order.waiter_name}`}</p>
          {(order.contact.name || order.mode !== "dine_in") && <p className="pos-context">
            {[order.contact.name, order.contact.phone, order.contact.address, order.contact.reference].filter(Boolean).join(" · ")}
          </p>}
          {typeof order.contact.estimated_at === "number" && <p className="pos-context">
            Entrega estimada · {shortTime(order.contact.estimated_at)}
          </p>}
          {order.mode === "delivery" && order.delivery_state && <PosState value={order.delivery_state} />}
          {order.notes && <p className="pos-context">{order.notes}</p>}
          {!liveLines.length && <p className="pos-empty">Selecciona productos del catálogo.</p>}
          <div className="pos-lines">{liveLines.map((line) => {
            const item = menu?.items.find((entry) => entry.id === line.item_id);
            const updateLine = (quantity: number) => run("edit", { item_id: line.item_id, line_id: line.id,
              variant_id: line.variant_id, modifier_ids: line.snapshot.modifiers.map((extra) => extra.id), quantity, notes: line.notes });
            return <article key={line.id} className="pos-line">
              <div><strong>{line.snapshot.name}</strong><small>{[
                line.snapshot.variant, ...line.snapshot.modifiers.map((extra) => extra.name), line.notes,
              ].filter(Boolean).join(" · ")}</small><PosState value={line.status} /></div>
              <div className="pos-line-price"><strong>{money(line.quantity * line.unit_cents - line.discount_cents)}</strong>
                <span aria-label="Cantidad">{line.quantity} × {money(line.unit_cents)}</span></div>
              {editable && (["new", "sent"].includes(line.status) || can("kitchen.adjust") ||
                can("kitchen.cancel") || can("orders.discount")) && <div className="pos-actions pos-line-buttons">
                {line.status === "new" && <>
                  <Button className="pos-button-small" variant="outline" disabled={transactions.pending || line.quantity <= 1}
                    aria-label={`Restar ${line.snapshot.name}`} onClick={() => void updateLine(line.quantity - 1)}>−</Button>
                  <Button className="pos-button-small" variant="outline" disabled={transactions.pending} aria-label={`Sumar ${line.snapshot.name}`}
                    onClick={() => void updateLine(line.quantity + 1)}>+</Button>
                </>}
                {item && (["new", "sent"].includes(line.status) || can("kitchen.adjust")) && <Button className="pos-button-small" variant="ghost"
                  onClick={() => setEditing({ item, line })}>Editar</Button>}
                {(["new", "sent"].includes(line.status) || can("kitchen.cancel")) && <Button className="pos-button-small" variant="ghost"
                  disabled={transactions.pending} onClick={() => line.status === "new" ? void run("remove", { line_id: line.id })
                    : setTool({ type: "remove", line })}>Retirar</Button>}
                {can("orders.discount") && <Button className="pos-button-small" variant="ghost"
                  onClick={() => setTool({ type: "discount", line })}>Descuento</Button>}
              </div>}
            </article>;
          })}</div>
          <dl className="pos-totals"><div><dt>Subtotal</dt><dd>{money(order.subtotal_cents)}</dd></div>
            <div><dt>Descuentos</dt><dd>{money(order.discount_cents)}</dd></div>
            {order.mode === "delivery" && <div><dt>Envío</dt><dd>{money(order.shipping_cents)}</dd></div>}
            <div><dt>Total</dt><dd>{money(order.total_cents)}</dd></div></dl>
          <PosState value={order.financial_status} />
          <div className="pos-actions pos-primary-actions">
            {editable && order.status === "draft" && <Button variant="outline" disabled={!liveLines.length || transactions.pending}
              onClick={() => void run("confirm", {}, "Pedido confirmado.")}>Guardar pedido</Button>}
            {mutable && can("kitchen.tickets.create") && <Button disabled={!ticketsPending || transactions.pending}
              onClick={() => void run("send", {}, "Comandas enviadas.")}>Enviar a cocina</Button>}
            {mutable && can("orders.request_bill") && <Button variant="outline" disabled={transactions.pending || (!liveLines.length || ticketsPending)}
              onClick={() => void run(order.financial_status === "bill_requested" ? "reopen_bill" : "bill")}>
              {order.financial_status === "bill_requested" ? "Reabrir cuenta" : "Solicitar cuenta"}</Button>}
            {mutable && can("orders.checkout") && order.financial_status === "bill_requested" &&
              <Button disabled title="Disponible en la Fase 7">Cobrar pedido</Button>}
          </div>
          <div className="pos-actions pos-secondary-actions">
            {can("receipts.preview") && <Button className="pos-button-small" variant="ghost" onClick={() => setTool({ type: "bill" })}>Ver cuenta</Button>}
            <Button className="pos-button-small" variant="ghost" onClick={() => setTool({ type: "history" })}>Actividad</Button>
            <Button className="pos-button-small" variant="ghost" onClick={() => setTool({ type: "tickets" })}>Comandas</Button>
            {editable && <Button className="pos-button-small" variant="ghost" onClick={() => setTool({ type: "details" })}>Datos del pedido</Button>}
            {mutable && order.mode === "dine_in" && can("orders.transfer") && <Button className="pos-button-small" variant="ghost"
              onClick={() => setTool({ type: "transfer" })}>Trasladar mesa</Button>}
            {mutable && liveLines.length > 0 && can("orders.split") && <Button className="pos-button-small" variant="ghost"
              onClick={() => setTool({ type: "split" })}>Dividir cuenta</Button>}
            {mutable && order.accounts.length > 1 && can("orders.merge") && <Button className="pos-button-small" variant="ghost"
              onClick={() => setTool({ type: "merge" })}>Combinar cuentas</Button>}
            {mutable && order.financial_status === "unpaid" && can("orders.discount") && <Button className="pos-button-small" variant="ghost"
              onClick={() => setTool({ type: "discount" })}>Aplicar descuento</Button>}
            {order.status === "ready" && can("orders.update") && <Button className="pos-button-small" variant="ghost"
              onClick={() => void run("deliver")}>{order.mode === "delivery" ? "Entregar al repartidor" : "Marcar entregado"}</Button>}
            {order.status === "delivered" && order.mode === "delivery" && order.delivery_state !== "delivered"
              && can("orders.update") && <Button className="pos-button-small" variant="ghost" onClick={() => void run("delivery", {
                state: order.delivery_state === "pending" ? "en_route" : "delivered",
              })}>{order.delivery_state === "pending" ? "Despachar entrega" : "Confirmar entrega"}</Button>}
            {mutable && can("orders.cancel") && <Button className="pos-button-small" variant="ghost"
              onClick={() => setTool({ type: "cancel" })}>Cancelar pedido</Button>}
          </div>
        </> : <p className="pos-empty">Abre un pedido existente o selecciona Nuevo pedido para comenzar.</p>}
      </aside>
    </div>
    {order && <Button className="pos-mobile-cart" onClick={() => setCart(!cart)}><ShoppingBasket size={18} />
      Pedido · {money(order.total_cents)}</Button>}
    {showStart && <StartOrder slug={slug} table={table} assign={can("orders.assign")} transactions={transactions}
      close={() => { setStart(false); if (table) navigate(); }} onCreated={(id) => { setStart(false); navigate(id); }} />}
    {editing && <ProductEditor key={editing.line?.id ?? editing.item.id} slug={slug} {...editing}
      busy={transactions.pending} message={transactions.message} close={() => setEditing(null)}
      save={async (body) => {
        if (await run(editing.line ? "edit" : "add", { ...body, line_id: editing.line?.id })) setEditing(null);
      }} />}
    {tool && order && <OrderTools key={tool.type} slug={slug} order={order} tool={tool} permissions={permissions}
      message={transactions.message} pending={transactions.pending} close={() => setTool(null)}
      save={async (op, body) => { if (await run(op, body)) setTool(null); }} />}
  </div>;
}

function StartOrder({ slug, table, assign, transactions, close, onCreated }: {
  slug: string; table?: string; assign: boolean; transactions: PosWrite; close: () => void; onCreated: (id: string) => void;
}) {
  const root = apiRoot(slug);
  const [customer, setCustomer] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [area, setArea] = useState("");
  const options = usePosData<PosOptions>(`${root}/pos/options?customer=`);
  const searchCustomers = usePosData<PosOptions>(`${root}/pos/options?customer=${encodeURIComponent(customer)}`,
    !!customer.trim());
  const customers = (customer.trim() ? searchCustomers.data : options.data)?.customers ?? [];
  const tables = usePosData<ServiceTable[]>(`${root}/service-tables`);
  const [selectedMode, setMode] = useState<Mode>();
  const modes = options.data?.mode_options ?? [];
  const mode = selectedMode ?? (table && modes.includes("dine_in") ? "dine_in" : modes[0]);
  const free = tables.data?.filter((entry) => entry.state === "available" && !entry.order_id) ?? [];
  const areas = [...new Set(free.map((entry) => entry.area))];
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const text = (key: string) => String(data.get(key) ?? "").trim();
    const result = await transactions.write("/orders", {
      request_id: uid(), mode, table_id: text("table") || null, guests: Number(text("guests")),
      customer_id: text("customer") || null, waiter_id: text("waiter") || null, name: text("name"),
      phone: text("phone"), address: text("address"), reference: text("reference"),
      notes: text("notes"), shipping_cents: text("fee") ? toCents(text("fee")) : 0,
      estimated_at: text("eta") ? Math.floor(Date.parse(`${text("eta")}-06:00`) / 1000) : null,
    }, "Borrador guardado.");
    if (result) onCreated(result.id);
  };
  return <Modal title="Nuevo pedido" close={close}>
    {transactions.message && <Message>{transactions.message}</Message>}
    {options.data && tables.data ? <form className="pos-form" onSubmit={submit}>
      <FieldRow label="Modalidad"><select value={mode ?? ""} onChange={(event) => setMode(event.target.value as Mode)}>
        {modes.map((entry) => <option value={entry} key={entry}>{caption(entry)}</option>)}
      </select></FieldRow>
      {mode === "dine_in" && <div className="pos-form-grid">
        <FieldRow label="Área del salón"><select value={area} onChange={(event) => setArea(event.target.value)}>
          <option value="">Todas las áreas</option>{areas.map((name) => <option key={name}>{name}</option>)}
        </select></FieldRow>
        <FieldRow label="Mesa disponible"><select key={area} name="table" required defaultValue={table ?? ""}>
          <option value="">Seleccionar mesa</option>
          {free.filter((entry) => !area || entry.area === area).map((entry) =>
            <option key={entry.id} value={entry.id}>{tableLabel(entry)} · {entry.area}</option>)}
        </select></FieldRow>
        <FieldRow label="Comensales"><input name="guests" type="number" min="0" max="1000" defaultValue="1" /></FieldRow>
      </div>}
      {assign && <FieldRow label="Mesero"><select name="waiter"><option value="">Mi usuario</option>
        {options.data.waiters.map((entry) => <option key={entry.id} value={entry.id}>{entry.name}</option>)}
      </select></FieldRow>}
      <FieldRow label="Buscar cliente registrado"><input value={customer} maxLength={100}
        onChange={(event) => setCustomer(event.target.value)} /></FieldRow>
      <FieldRow label="Cliente registrado"><select name="customer" value={customerId} onChange={(event) => {
        setCustomerId(event.target.value);
        setCustomerName(event.target.selectedOptions[0].text);
      }}><option value="">Sin seleccionar</option>
        {customerId && !customers.some((entry) => entry.id === customerId) &&
          <option value={customerId}>{customerName}</option>}
        {customers.map((entry) => <option key={entry.id} value={entry.id}>{entry.name}</option>)}
      </select></FieldRow>
      {mode !== "dine_in" && <>
        <div className="pos-form-grid"><FieldRow label="Nombre"><input name="name" maxLength={1000} /></FieldRow>
          <FieldRow label="Teléfono"><input name="phone" type="tel" maxLength={1000} /></FieldRow>
        </div>
        <FieldRow label="Hora estimada"><input name="eta" type="datetime-local" /></FieldRow>
      </>}
      {mode === "delivery" && <>
        <FieldRow label="Dirección"><input name="address" maxLength={1000} /></FieldRow>
        <FieldRow label="Referencia"><input name="reference" maxLength={1000} /></FieldRow>
        <FieldRow label="Costo de envío (Q)"><input name="fee" type="number" min="0" max="1000000" step="0.01" /></FieldRow>
      </>}
      <FieldRow label="Observaciones del pedido"><textarea name="notes" maxLength={1000} /></FieldRow>
      <Button disabled={!mode || (mode === "dine_in" && !free.length) || transactions.pending} type="submit">
        Crear borrador <ArrowRight size={16} /></Button>
    </form> : <Load error={options.error ?? tables.error} retry={() => {
      void options.refetch(); void tables.refetch();
    }} />}
  </Modal>;
}

function ProductEditor({ slug, item, line, close, save, busy, message }: {
  slug: string; item: Item; line?: OrderLine; close: () => void; busy: boolean; message: string;
  save: (body: object) => Promise<void>;
}) {
  const [variant, setVariant] = useState(line?.variant_id ?? "");
  const [extras, setExtras] = useState(line?.snapshot.modifiers.map((extra) => extra.id) ?? []);
  const [quantity, setQuantity] = useState(line?.quantity ?? 1);
  const [notes, setNotes] = useState(line?.notes ?? "");
  const configuredVariants = item.variants.filter((entry) => entry.available || entry.id === line?.variant_id);
  const adjusted = configuredVariants.find((entry) => entry.id === variant);
  const formerVariant = line?.variant_id && !configuredVariants.some((entry) => entry.id === line.variant_id);
  const currentExtras = new Set(item.modifier_groups.flatMap((group) => group.modifiers.map((extra) => extra.id)));
  const formerExtras = line?.snapshot.modifiers.filter((extra) => !currentExtras.has(extra.id)) ?? [];
  const estimate = (adjusted?.pricing === "replace" ? adjusted.price_cents : item.price_cents + (adjusted?.price_cents ?? 0))
    + item.modifier_groups.flatMap((group) => group.modifiers).filter((extra) => extras.includes(extra.id))
      .reduce((sum, extra) => sum + extra.price_cents, 0);
  const sameSelection = line && variant === (line.variant_id ?? "") && extras.length === line.snapshot.modifiers.length
    && line.snapshot.modifiers.every((extra) => extras.includes(extra.id));
  const valid = sameSelection || item.modifier_groups.every((group) => {
    const count = group.modifiers.filter((extra) => extras.includes(extra.id)).length;
    return count >= group.minimum && count <= group.maximum;
  });
  return <Modal title={line ? `Editar ${item.name}` : item.name} close={close}>
    <form className="pos-form" onSubmit={(event) => {
      event.preventDefault();
      const reason = String(new FormData(event.currentTarget).get("reason") ?? "").trim();
      void save({ item_id: item.id, variant_id: variant || null, modifier_ids: extras, quantity, notes, reason: reason || null });
    }}>
      {message && <Message>{message}</Message>}
      <div className="pos-product-preview"><Photo slug={slug} id={item.image_id} alt="" /><div><p>{item.description}</p><b>Precio base {money(item.price_cents)}</b></div></div>
      {(configuredVariants.length > 0 || formerVariant) && <FieldRow label="Variante"><select value={variant} onChange={(event) => setVariant(event.target.value)}>
        <option value="">Presentación base</option>
        {formerVariant && <option value={line?.variant_id ?? ""}>{line?.snapshot.variant} · Histórica</option>}
        {configuredVariants.map((entry) => <option value={entry.id} key={entry.id} disabled={!entry.available}>
          {entry.name} · {entry.pricing === "replace" ? money(entry.price_cents) : `ajuste ${money(entry.price_cents)}`}
        </option>)}
      </select></FieldRow>}
      {item.modifier_groups.map((group) => <fieldset className="restaurant-fieldset" key={group.id}>
        <legend>{group.name} ({group.minimum}–{group.maximum})</legend>
        {group.modifiers.map((extra) => <label className="check" key={extra.id}>
          <input type="checkbox" checked={extras.includes(extra.id)} onChange={(event) =>
            setExtras(event.target.checked ? [...extras, extra.id] : extras.filter((entry) => entry !== extra.id))} />
          {extra.name} · {money(extra.price_cents)}
        </label>)}
      </fieldset>)}
      {formerExtras.length > 0 && <fieldset className="restaurant-fieldset"><legend>Extras históricos</legend>
        {formerExtras.map((extra) => <label key={extra.id} className="check">
          <input type="checkbox" checked={extras.includes(extra.id)} onChange={(event) => setExtras(event.target.checked
            ? [...extras, extra.id] : extras.filter((entry) => entry !== extra.id))} />
          {extra.name} · {money(extra.price_cents)}
        </label>)}
      </fieldset>}
      <FieldRow label="Cantidad"><input type="number" min="1" max="1000" required value={quantity}
        onChange={(event) => setQuantity(Number(event.target.value))} /></FieldRow>
      <FieldRow label="Observaciones del producto"><textarea value={notes} maxLength={1000}
        onChange={(event) => setNotes(event.target.value)} placeholder="Ej. sin hielo" /></FieldRow>
      {line && line.status !== "new" && <FieldRow label="Motivo del ajuste"><input name="reason" required minLength={3} maxLength={1000} /></FieldRow>}
      <Button type="submit" disabled={!valid || !quantity || busy}>{line ? "Guardar producto" : "Agregar al pedido"}
        {" · "}{money((sameSelection ? line.unit_cents : estimate) * quantity)}</Button>
    </form>
  </Modal>;
}
