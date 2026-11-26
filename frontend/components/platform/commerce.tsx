"use client";

import Image from "next/image";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { money, type Member, type Plan, type Restaurant, type Team } from "@/lib/api";
import {
  cents, day, entries, errorText, Fields, fileContent, formatDate, getText, Heading, label, lines,
  Load, Modal, NewButton, Note, panelError, Pill, queryString, Save, Table, useChange, useData,
  utcDate, type FormField,
} from "./shared";

interface CatalogPlan extends Plan {
  description: string; annual_cents: number | null; features: string[]; trial_days: number;
  grace_days: number; revision: number; active: boolean; restaurants: number;
}
type Version = Omit<CatalogPlan, "code" | "active" | "restaurants"> & { id: string; created_at: number };
interface Subscription {
  id: string; restaurant: string; restaurant_name: string; plan: string; plan_code: string;
  revision: number; starts_on: string; ends_on: string; trial_until: string | null;
  cycle: string; grace_days: number; price_cents: number; discount_cents: number; state: string;
}
interface Period {
  id: string; starts_on: string; ends_on: string; due_cents: number; balance_cents: number;
  paid_cents: number; kind: string; applied: boolean;
}
interface History { id: string; action: string; created_at: number; snapshot: { plan: string; revision: number; ends_on: string; state: string } }
interface SubscriptionDetail extends Subscription { periods: Period[]; history: History[] }
interface Payment {
  id: string; restaurant_name: string; restaurant: string; amount_cents: number; method: string;
  reference: string; paid_on: string; state: string; actor: string; has_receipt: boolean;
  starts_on: string; ends_on: string; notes: string;
}
interface RestaurantDetail extends Restaurant {
  legal_name: string; tax_id: string; owner: string; phone: string; contact_email: string;
  address: string; notes: string; logo_url: string; subscription: Subscription | null;
}
type Activity = { id: string; action: string; created_at: number; result: string };

const required = (name: string, label: string, type?: FormField["type"]): FormField =>
  ({ name, label, type, required: true });
const number = (name: string, label: string, min = 0, step?: string): FormField =>
  ({ name, label, type: "number", min, step, required: true });
const choices = (list: string[]) => list.map((value) => ({ value, label: label(value) }));
const catalog = "/platform/plan-catalog";
const codeFields: FormField[] = [
  required("name", "Nombre"), { name: "description", label: "Descripción", type: "textarea" },
  number("monthly", "Precio mensual (Q)", 0, "0.01"),
  { name: "annual", label: "Precio anual (Q)", type: "number", min: 0, step: "0.01" },
  number("max_admins", "Administradores", 1), number("max_staff", "Operativos"),
  number("max_total", "Cupo total", 1), number("trial_days", "Días de prueba"),
  number("grace_days", "Días de gracia"),
  { name: "features", label: "Funcionalidades (una por línea)", type: "textarea" },
  { name: "fel_enabled", label: "FEL habilitada para el plan", type: "checkbox" },
  { name: "active", label: "Plan disponible para nuevas asignaciones", type: "checkbox" },
];

function PlanEditor({ plan, close, done }: { plan?: CatalogPlan; close: () => void; done: () => void }) {
  const change = useChange(done);
  function submit(event: FormEvent<HTMLFormElement>) {
    const data = entries(event);
    const annual = getText(data, "annual");
    change.mutate({
      path: plan ? `/platform/plans/${plan.code}` : "/platform/plans",
      method: plan ? "PUT" : "POST",
      body: {
        code: getText(data, "code"), name: getText(data, "name"), description: getText(data, "description"),
        monthly_cents: cents(getText(data, "monthly")), annual_cents: annual ? cents(annual) : null,
        max_admins: Number(data.get("max_admins")), max_staff: Number(data.get("max_staff")),
        max_total: Number(data.get("max_total")), trial_days: Number(data.get("trial_days")),
        grace_days: Number(data.get("grace_days")), features: lines(data, "features"),
        fel_enabled: data.has("fel_enabled"), active: data.has("active"),
      },
    });
  }
  return <Modal title={plan ? "Editar plan" : "Crear plan"} close={close}>
    {plan && <p>Los contratos existentes conservan su versión actual.</p>}
    <form onSubmit={submit}>
      <Fields fields={plan ? codeFields : [required("code", "Código"), ...codeFields]} initial={plan ? {
        ...plan, monthly: plan.monthly_cents / 100, annual: plan.annual_cents === null ? "" : plan.annual_cents / 100,
        features: plan.features.join("\n"),
      } : { active: true, monthly: 0, max_admins: 1, max_staff: 4, max_total: 5, trial_days: 0, grace_days: 0 }} />
      {panelError(change.error)}<Save pending={change.isPending}>{plan ? "Guardar plan" : "Crear plan"}</Save>
    </form>
  </Modal>;
}

function Versions({ plan, close }: { plan: CatalogPlan; close: () => void }) {
  const query = useData<Version[]>(`/platform/plans/${plan.code}/versions`);
  return <Modal title={`Versiones de ${plan.name}`} close={close}>
    {query.data ? <Table rows={query.data} rowKey={(row) => row.id} columns={[
      { label: "Revisión", cell: (row) => row.revision },
      { label: "Vigente desde", cell: (row) => formatDate(row.created_at) },
      { label: "Mensual", cell: (row) => money(row.monthly_cents) },
      { label: "Anual", cell: (row) => row.annual_cents === null ? "—" : money(row.annual_cents) },
      { label: "Cupos (adm./op./total)", cell: (row) => `${row.max_admins}/${row.max_staff}/${row.max_total}` },
    ]} /> : <Load error={query.error} retry={query.refetch} />}
  </Modal>;
}

export function PlanCatalog({ open }: { open: boolean }) {
  const query = useData<CatalogPlan[]>(catalog);
  const [editor, setEditor] = useState<CatalogPlan | true | null>(open ? true : null);
  const [versions, setVersions] = useState<CatalogPlan | null>(null);
  const [notice, setNotice] = useState("");
  const change = useChange(() => setNotice("Estado del plan guardado."));
  return <>
    <Heading title="Planes" text="Administra precios, cupos y condiciones comerciales."
      action={<NewButton onClick={() => setEditor(true)}>Crear plan</NewButton>} />
    <Note>{notice}</Note>{panelError(change.error)}
    {query.data ? <div className="commercial-plan-grid">{query.data.map((plan) => <article className="panel commercial-plan" key={plan.code}>
      <div className="commercial-row"><h2>{plan.name}</h2><Pill value={plan.active ? "active" : "Archivado"} /></div>
      <p className="plan-price">{money(plan.monthly_cents)} <small>/ mes</small></p>
      {plan.annual_cents !== null && <p>{money(plan.annual_cents)} al año</p>}
      {plan.description && <p>{plan.description}</p>}
      <dl className="commercial-summary">
        <div><dt>Administradores</dt><dd>{plan.max_admins}</dd></div>
        <div><dt>Operativos</dt><dd>{plan.max_staff}</dd></div>
        <div><dt>Cupo total</dt><dd>{plan.max_total}</dd></div>
        <div><dt>Restaurantes</dt><dd>{plan.restaurants}</dd></div>
        <div><dt>Revisión</dt><dd>{plan.revision}</dd></div>
      </dl>
      <p>{plan.fel_enabled ? "FEL habilitada por plan" : "FEL deshabilitada por plan"}</p>
      <div className="commercial-actions">
        <Button variant="outline" onClick={() => setEditor(plan)}>Editar</Button>
        <Button variant="ghost" onClick={() => setVersions(plan)}>Versiones</Button>
        {plan.active && <Button variant="ghost" disabled={change.isPending} onClick={() => {
          if (window.confirm(`¿Archivar el plan ${plan.name}?`)) change.mutate({ path: `/platform/plans/${plan.code}`, method: "DELETE" });
        }}>Archivar</Button>}
      </div>
    </article>)}</div> : <Load error={query.error} retry={query.refetch} />}
    {editor && <PlanEditor plan={editor === true ? undefined : editor} close={() => setEditor(null)}
      done={() => { setEditor(null); setNotice("Plan guardado."); }} />}
    {versions && <Versions plan={versions} close={() => setVersions(null)} />}
  </>;
}

const subscriptionStatuses = ["active", "trial", "pending", "grace", "expired", "suspended", "cancelled"];
const cycles = choices(["monthly", "annual"]);
const cycleField: FormField = { ...required("cycle", "Ciclo", "select"), items: cycles };
const discountField = number("discount", "Descuento por período (Q)", 0, "0.01");
function usePlanOptions() {
  const query = useData<Plan[]>("/platform/subscription-plans");
  return query.data?.map((plan) => ({ value: plan.code, label: plan.name })) ?? [];
}

function SubscriptionEditor({ close, done, restaurant }: { close: () => void; done: () => void; restaurant?: string }) {
  const plans = usePlanOptions();
  const restaurants = useData<{ slug: string; name: string }[]>("/platform/subscription-restaurants");
  const change = useChange(done);
  const fields: FormField[] = [
    { ...required("restaurant", "Restaurante", "select"),
      items: restaurants.data?.map((row) => ({ value: row.slug, label: row.name })) },
    { ...required("plan_code", "Plan", "select"), items: plans }, cycleField,
    required("starts_on", "Inicio", "date"), required("ends_on", "Vencimiento", "date"), discountField,
    { name: "trial_days", label: "Días de prueba", type: "number", min: 0, max: 90, hint: "Vacío usa el plan." },
    { name: "grace_days", label: "Días de gracia", type: "number", min: 0, max: 90, hint: "Vacío usa el plan." },
    { name: "pending", label: "Activar al cubrir el primer período", type: "checkbox" },
  ];
  return <Modal title="Nueva suscripción" close={close}>
    <form onSubmit={(event) => {
      const data = entries(event);
      const optionalDays = (key: string) => getText(data, key) ? Number(getText(data, key)) : null;
      change.mutate({ path: "/platform/subscriptions", body: {
        restaurant: getText(data, "restaurant"), plan_code: getText(data, "plan_code"),
        starts_on: getText(data, "starts_on"), ends_on: getText(data, "ends_on"), cycle: getText(data, "cycle"),
        discount_cents: cents(getText(data, "discount")), trial_days: optionalDays("trial_days"),
        grace_days: optionalDays("grace_days"), pending: data.has("pending"),
      } });
    }}>
      <Fields fields={fields} initial={{ restaurant, cycle: "monthly", starts_on: utcDate(), discount: 0, pending: true }} />
      {panelError(change.error || restaurants.error)}<Save pending={change.isPending}>Crear suscripción</Save>
    </form>
  </Modal>;
}

function HistoryTable({ rows }: { rows: History[] }) {
  return <Table rows={rows} rowKey={(row) => row.id} columns={[
    { label: "Acción", cell: (row) => row.action },
    { label: "Fecha", cell: (row) => formatDate(row.created_at) },
    { label: "Plan y versión", cell: (row) => `${row.snapshot.plan} · v${row.snapshot.revision}` },
    { label: "Vencimiento", cell: (row) => day(row.snapshot.ends_on) },
    { label: "Estado", cell: (row) => <Pill value={row.snapshot.state} /> },
  ]} />;
}

function SubscriptionInspect({ selected, close }: { selected: Subscription; close: () => void }) {
  const endpoint = `/platform/subscriptions/${selected.id}`;
  const query = useData<SubscriptionDetail>(endpoint);
  const plans = usePlanOptions();
  const [mode, setMode] = useState<"renew" | "plan" | "terms" | null>(null);
  const [initialTerms, setInitialTerms] = useState(false);
  const [notice, setNotice] = useState("");
  const change = useChange(() => { setMode(null); setNotice("Suscripción actualizada."); });
  const row = query.data;
  function submit(event: FormEvent<HTMLFormElement>) {
    const data = entries(event);
    if (mode === "renew") change.mutate({ path: `${endpoint}/renewals`,
      body: { starts_on: getText(data, "starts_on"), ends_on: getText(data, "ends_on") } });
    else if (mode === "terms") change.mutate({ path: `${endpoint}/terms`, method: "PUT", body: {
      grace_days: Number(data.get("grace_days")),
      ...(initialTerms ? { starts_on: getText(data, "starts_on"), ends_on: getText(data, "ends_on"),
        discount_cents: cents(getText(data, "discount")), trial_days: Number(data.get("trial_days")) } : {}),
    } });
    else change.mutate({ path: `${endpoint}/plan`, body: {
      plan_code: getText(data, "plan_code"), cycle: getText(data, "cycle"),
      discount_cents: cents(getText(data, "discount")),
    } });
  }
  return <Modal title={selected.restaurant_name} close={close}>
    <Note>{notice}</Note>{panelError(change.error)}
    {row ? <div className="commercial-stack">
      <div className="commercial-row"><p>{row.plan} · v{row.revision} · {money(row.price_cents - row.discount_cents)}</p><Pill value={row.state} /></div>
      <p>Vence el {day(row.ends_on)} · {row.grace_days} días de gracia
        {row.trial_until && ` · Prueba hasta ${day(row.trial_until)}`}</p>
      {row.state !== "cancelled" && <div className="commercial-actions">
        <Button variant="outline" onClick={() => setMode("renew")}>Preparar renovación</Button>
        <Button variant="outline" onClick={() => setMode("plan")}>Cambiar plan</Button>
        <Button variant="outline" onClick={() => { setMode("terms"); setInitialTerms(false); }}>Editar vigencia y gracia</Button>
        {[row.state === "suspended" ? ["resume", "Reactivar"] : ["suspend", "Suspender"], ["cancel", "Cancelar"]].map(
          ([action, caption]) => <Button key={action} variant="ghost" disabled={change.isPending} onClick={() => {
            if (window.confirm(`¿${caption} la suscripción?`)) change.mutate({ path: `${endpoint}/state`, body: { action } });
          }}>{caption}</Button>)}
      </div>}
      {mode && <form onSubmit={submit} key={mode} className="commercial-inset">
        {mode === "terms" && <label className="check"><input type="checkbox" checked={initialTerms}
          onChange={(event) => setInitialTerms(event.target.checked)} /> Editar el período inicial (antes de registrar pagos)</label>}
        <Fields fields={mode === "renew" ? [required("starts_on", "Inicio", "date"), required("ends_on", "Vencimiento", "date")]
          : mode === "terms" ? [number("grace_days", "Días de gracia"), ...(initialTerms ? [
            required("starts_on", "Inicio", "date"), required("ends_on", "Vencimiento", "date"),
            number("trial_days", "Días de prueba"), discountField,
          ] : [])] : [{ ...required("plan_code", "Plan", "select"), items: plans }, cycleField, discountField]}
          initial={{ starts_on: mode === "renew" ? row.ends_on : row.starts_on,
            ends_on: mode === "terms" ? row.ends_on : "", cycle: row.cycle, plan_code: row.plan_code,
            discount: row.discount_cents / 100, grace_days: row.grace_days, trial_days: row.trial_until
              ? (Date.parse(row.trial_until) - Date.parse(row.starts_on)) / 86_400_000 : 0 }} />
        <Save pending={change.isPending}>{mode === "renew" ? "Crear período de renovación"
          : mode === "terms" ? "Guardar condiciones" : "Aplicar cambio de plan"}</Save>
      </form>}
      <h2>Períodos de cobro</h2>
      <Table rows={row.periods} rowKey={(period) => period.id} columns={[
        { label: "Período", cell: (period) => `${day(period.starts_on)} a ${day(period.ends_on)}` },
        { label: "Importe", cell: (period) => money(period.due_cents) },
        { label: "Pagado", cell: (period) => money(period.paid_cents) },
        { label: "Saldo", cell: (period) => money(period.balance_cents) },
        { label: "Acción", cell: (period) => period.balance_cents > 0 &&
          <Link className="text-link" href={`/platform/payments?new=1&subscription=${row.id}&period=${period.id}`}>Registrar pago</Link> },
      ]} />
      <h2>Historial</h2><HistoryTable rows={row.history} />
    </div> : <Load error={query.error} retry={query.refetch} />}
  </Modal>;
}

function Filters({ filters, onChange, states: options, plan = false }: {
  filters: Record<string, string>; onChange: (name: string, value: string) => void;
  states?: string[]; plan?: boolean;
}) {
  const plans = useData<{ code: string; name: string }[]>("/platform/subscription-plans", plan);
  return <div className="commercial-filters panel">
    <label>Identificador de restaurante<input value={filters.restaurant ?? ""} placeholder="ejemplo-restaurante"
      onChange={(event) => onChange("restaurant", event.target.value)} /></label>
    {options && <label>Estado<select value={filters.state ?? ""} onChange={(event) => onChange("state", event.target.value)}>
      <option value="">Todos</option>{options.map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>}
    {plan && <label>Plan<select value={filters.plan ?? ""} onChange={(event) => onChange("plan", event.target.value)}>
      <option value="">Todos</option>{plans.data?.map((value) => <option key={value.code} value={value.code}>{value.name}</option>)}</select></label>}
    {["start", "end"].map((key) => <label key={key}>{key === "start" ? "Desde" : "Hasta"}<input type="date"
      value={filters[key] ?? ""} onChange={(event) => onChange(key, event.target.value)} /></label>)}
  </div>;
}

export function Subscriptions({ open, restaurant }: { open: boolean; restaurant?: string }) {
  const [creating, setCreating] = useState(open);
  const [selected, setSelected] = useState<Subscription | null>(null);
  const [filters, setFilters] = useState<Record<string, string>>({ restaurant: restaurant ?? "" });
  const [notice, setNotice] = useState("");
  const query = useData<Subscription[]>(`/platform/subscriptions?${queryString(filters)}`);
  const update = (name: string, value: string) => setFilters((current) => ({ ...current, [name]: value }));
  return <>
    <Heading title="Suscripciones" text="Administra vigencia, renovaciones y cambios de plan."
      action={<NewButton onClick={() => setCreating(true)}>Nueva suscripción</NewButton>} />
    <Note>{notice}</Note><Filters filters={filters} onChange={update} states={subscriptionStatuses} plan />
    {query.data ? <Table rows={query.data} rowKey={(row) => row.id} columns={[
      { label: "Restaurante", cell: (row) => <button className="text-link" onClick={() => setSelected(row)}>{row.restaurant_name}</button> },
      { label: "Plan", cell: (row) => `${row.plan} · v${row.revision}` },
      { label: "Importe", cell: (row) => money(row.price_cents - row.discount_cents) },
      { label: "Vencimiento", cell: (row) => day(row.ends_on) },
      { label: "Estado", cell: (row) => <Pill value={row.state} /> },
      { label: "Acciones", cell: (row) => <Button variant="ghost" onClick={() => setSelected(row)}>Ver historial</Button> },
    ]} /> : <Load error={query.error} retry={query.refetch} />}
    {creating && <SubscriptionEditor close={() => setCreating(false)} restaurant={restaurant}
      done={() => { setCreating(false); setNotice("Suscripción creada."); }} />}
    {selected && <SubscriptionInspect selected={selected} close={() => setSelected(null)} />}
  </>;
}

function PaymentEditor({ close, done, subscription, period }: {
  close: () => void; done: () => void; subscription?: string; period?: string;
}) {
  const [selected, setSelected] = useState(subscription ?? "");
  const [selectedPeriod, setSelectedPeriod] = useState(period ?? "");
  const [key] = useState(() => crypto.randomUUID());
  const [error, setError] = useState("");
  const [reading, setReading] = useState(false);
  const subs = useData<Subscription[]>("/platform/payment-subscriptions");
  const periods = useData<Period[]>(`/platform/payment-subscriptions/${selected}/periods`, Boolean(selected));
  const methods = useData<string[]>("/platform/payment-methods");
  const change = useChange(done);
  async function submit(event: FormEvent<HTMLFormElement>) {
    const data = entries(event);
    const receipt = data.get("receipt");
    setError(""); setReading(true);
    try {
      change.mutate({ path: "/platform/payments", body: {
        period_id: selectedPeriod, amount_cents: cents(getText(data, "amount")),
        method: getText(data, "method"), reference: getText(data, "reference"),
        paid_on: getText(data, "paid_on"), notes: getText(data, "notes"), request_key: key,
        receipt: receipt instanceof File && receipt.size ? await fileContent(receipt) : null,
      } });
    } catch (reason) { setError(errorText(reason)); }
    finally { setReading(false); }
  }
  return <Modal title="Registrar pago" close={close}>
    <form onSubmit={submit}>
      <div className="commercial-fields">
        <label className="field">Suscripción<select required value={selected} onChange={(event) => {
          setSelected(event.target.value); setSelectedPeriod("");
        }}><option value="">Seleccionar</option>{subs.data?.map((row) =>
          <option key={row.id} value={row.id}>{row.restaurant_name} · {row.plan}</option>)}</select></label>
        <label className="field">Período<select required value={selectedPeriod} onChange={(event) => setSelectedPeriod(event.target.value)}>
          <option value="">Seleccionar</option>{periods.data?.filter((row) => row.balance_cents > 0).map((row) =>
            <option key={row.id} value={row.id}>{day(row.starts_on)} · Saldo {money(row.balance_cents)}</option>)}</select></label>
      </div>
      <Fields fields={[
        number("amount", "Monto (Q)", 0.01, "0.01"), required("paid_on", "Fecha de pago", "date"),
        { ...required("method", "Método", "select"), items: choices(methods.data ?? []) },
        { name: "reference", label: "Referencia" }, { name: "notes", label: "Observaciones", type: "textarea" },
        { name: "receipt", label: "Comprobante adjunto", type: "file", accept: "image/png,image/jpeg,image/webp" },
      ]} initial={{ paid_on: utcDate() }} />
      {error && <p className="field-error" role="alert">{error}</p>}
      {panelError(change.error || subs.error || periods.error || methods.error)}
      <Save pending={change.isPending || reading}>Registrar pago</Save>
    </form>
  </Modal>;
}

function PaymentTable({ rows, action }: { rows: Payment[]; action?: (row: Payment) => React.ReactNode }) {
  return <Table rows={rows} rowKey={(row) => row.id} columns={[
    { label: "Restaurante", cell: (row) => row.restaurant_name },
    { label: "Fecha", cell: (row) => day(row.paid_on) },
    { label: "Monto", cell: (row) => money(row.amount_cents) },
    { label: "Método", cell: (row) => row.method },
    { label: "Referencia", cell: (row) => row.reference || "—" },
    { label: "Estado", cell: (row) => <Pill value={row.state} /> },
    { label: "Registró", cell: (row) => row.actor },
    ...(action ? [{ label: "Acciones", cell: action }] : []),
  ]} />;
}

export function Payments({ open, subscription, period }: { open: boolean; subscription?: string; period?: string }) {
  const [creating, setCreating] = useState(open);
  const [selection, setSelection] = useState<Payment | null>(null);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("");
  const encoded = queryString(filters);
  const query = useData<Payment[]>(`/platform/payments?${encoded}`);
  const change = useChange(() => { setSelection(null); setNotice("Estado del pago guardado."); });
  return <>
    <Heading title="Pagos" text="Consulta y confirma cobros de suscripciones."
      action={<NewButton onClick={() => setCreating(true)}>Registrar pago</NewButton>} />
    <Note>{notice}</Note>
    <Filters filters={filters} onChange={(name, value) => setFilters((current) => ({ ...current, [name]: value }))}
      states={["pending", "confirmed", "rejected", "reversed"]} />
    <div className="commercial-actions export-actions">
      {["csv", "pdf"].map((format) => <Button key={format} asChild variant="outline">
        <a href={`/api/platform/payments-export/${format}?${encoded}`}>Exportar {format.toUpperCase()}</a>
      </Button>)}
    </div>
    {query.data ? <PaymentTable rows={query.data} action={(row) =>
      <Button variant="ghost" onClick={() => { change.reset(); setSelection(row); }}>Ver pago</Button>} />
      : <Load error={query.error} retry={query.refetch} />}
    {creating && <PaymentEditor subscription={subscription} period={period} close={() => setCreating(false)}
      done={() => { setCreating(false); setNotice("Pago registrado. Confírmalo cuando corresponda."); }} />}
    {selection && <Modal title={`Pago de ${selection.restaurant_name}`} close={() => setSelection(null)}>
      <div className="commercial-stack">
        <p>{money(selection.amount_cents)} · {selection.method} · {day(selection.paid_on)}</p>
        <p>Período {day(selection.starts_on)} a {day(selection.ends_on)} · {label(selection.state)}</p>
        {selection.notes && <p>{selection.notes}</p>}
        {selection.has_receipt && <a className="text-link" href={`/api/platform/payments/${selection.id}/receipt`}>Descargar comprobante</a>}
        {panelError(change.error)}
        <div className="commercial-actions">
          {(selection.state === "pending" ? [["confirm", "Confirmar pago"], ["reject", "Rechazar pago"]]
            : selection.state === "confirmed" ? [["reverse", "Revertir pago"]] : []).map(([action, caption]) =>
            <Button key={action} disabled={change.isPending} onClick={() => {
              if (window.confirm(`¿${caption}?`)) change.mutate({ path: `/platform/payments/${selection.id}/state`, body: { action } });
            }}>{caption}</Button>)}
        </div>
      </div>
    </Modal>}
  </>;
}

const detailFields: FormField[] = [
  required("name", "Nombre comercial"), { name: "legal_name", label: "Razón social" },
  { name: "tax_id", label: "NIT" }, { name: "owner", label: "Propietario" }, { name: "phone", label: "Teléfono" },
  { name: "contact_email", label: "Correo", type: "email" }, { name: "address", label: "Dirección", type: "textarea" },
  { name: "logo_url", label: "URL del logotipo" },
];

export function RestaurantView({ slug, subscriptionAccess }: { slug: string; subscriptionAccess: boolean }) {
  const path = `/platform/restaurants/${slug}`;
  const query = useData<RestaurantDetail>(path);
  const [tab, setTab] = useState("Información general");
  const [invite, setInvite] = useState(false);
  const [notice, setNotice] = useState("");
  const [selected, setSelected] = useState<Subscription | null>(null);
  const team = useData<Team>(`${path}/members`, tab === "Usuarios" || invite);
  const history = useData<{ subscription: History[]; payments: Payment[]; activity: Activity[] }>(
    `${path}/history`, ["Suscripción", "Pagos", "Actividad"].includes(tab));
  const change = useChange(() => { setNotice("Cambios guardados."); });
  const invitation = useChange<{ status: string }>((result) => {
    setInvite(false); setNotice(result.status === "simulated" ? "Invitación simulada." : "Invitación enviada.");
  });
  const row = query.data;
  if (!row) return <Load error={query.error} retry={query.refetch} />;
  function edit(event: FormEvent<HTMLFormElement>) {
    const values = entries(event);
    const payload = Object.fromEntries(detailFields.map(({ name }) =>
      [name, values.has(name) ? getText(values, name) : row?.[name as keyof RestaurantDetail]]));
    change.mutate({ path, method: "PUT", body: { ...payload, notes: values.has("notes") ? getText(values, "notes") : row?.notes } });
  }
  return <>
    <Link className="text-link" href="/platform/restaurants">Volver al directorio</Link>
    <div className="detail-title"><Heading title={row.name} text={`${row.plan.name} · Alta ${formatDate(row.created_at)}`}
      action={<Button variant="outline" disabled={change.isPending} onClick={() => {
        if (window.confirm(row.active ? "¿Suspender este restaurante?" : "¿Reactivar este restaurante?"))
          change.mutate({ path: `${path}/active`, body: { active: !row.active } });
      }}>{row.active ? "Suspender" : "Reactivar"}</Button>} /></div>
    <Note>{notice}</Note>{panelError(change.error)}
    <div className="panel commercial-inset restaurant-seats">
      <div className="commercial-row"><Pill value={row.active ? "active" : "suspended"} />
        <p>{row.subscription ? `Contrato ${money(row.subscription.price_cents - row.subscription.discount_cents)} · vence ${day(row.subscription.ends_on)}`
          : "Asignación inicial sin suscripción"}</p>
        {row.logo_url && <a href={row.logo_url} target="_blank" rel="noreferrer" aria-label="Abrir logotipo">
          <Image src={row.logo_url} alt={`Logotipo de ${row.name}`} width={48} height={48} unoptimized
            referrerPolicy="no-referrer" style={{ objectFit: "contain", borderRadius: 6 }} />
        </a>}
      </div>
      <div className="seats-grid">{[
        ["Administradores", row.usage.admins, row.plan.max_admins],
        ["Operativos", row.usage.staff, row.plan.max_staff],
        ["Total", row.usage.total, row.plan.max_total],
      ].map(([name, used, max]) => <div key={name}><p>{name} · {used}/{max}</p><progress value={used} max={Number(max) || 1} aria-label={String(name)} /></div>)}</div>
    </div>
    <nav className="commercial-tabs" aria-label="Detalle del restaurante">{[
      "Información general", "Usuarios", "Suscripción", "Pagos", "Configuración fiscal", "Actividad", "Observaciones",
    ].map((caption) => <Button key={caption} variant={tab === caption ? "outline" : "ghost"} aria-pressed={tab === caption}
      onClick={() => { setTab(caption); setNotice(""); change.reset(); }}>{caption}</Button>)}</nav>
    {tab === "Información general" && <form className="panel commercial-inset" onSubmit={edit}>
      <Fields fields={detailFields} initial={{ ...row }} /><Save pending={change.isPending} />
    </form>}
    {tab === "Observaciones" && <form className="panel commercial-inset" onSubmit={edit}>
      <Fields fields={[{ name: "notes", label: "Observaciones internas", type: "textarea" }]} initial={{ notes: row.notes }} />
      <Save pending={change.isPending} />
    </form>}
    {tab === "Usuarios" && <div className="commercial-stack">
      <div className="commercial-actions"><NewButton onClick={() => setInvite(true)}>Invitar usuario</NewButton></div>
      {team.data ? <Table rows={team.data.items} rowKey={(member: Member) => member.email} columns={[
        { label: "Nombre", cell: (member) => member.name }, { label: "Correo", cell: (member) => member.email },
        { label: "Rol", cell: (member) => member.role }, { label: "Estado", cell: (member) => <Pill value={member.active ? "active" : "suspended"} /> },
      ]} /> : <Load error={team.error} retry={team.refetch} />}
    </div>}
    {tab === "Suscripción" && <div className="commercial-stack">
      {subscriptionAccess && (row.subscription
        ? <Button variant="outline" onClick={() => setSelected(row.subscription)}>Gestionar suscripción</Button>
        : <Button asChild><Link href={`/platform/subscriptions?new=1&restaurant=${slug}`}>Asignar suscripción</Link></Button>)}
      {history.data ? <HistoryTable rows={history.data.subscription} /> : <Load error={history.error} retry={history.refetch} />}
    </div>}
    {tab === "Pagos" && (history.data ? <PaymentTable rows={history.data.payments} /> : <Load error={history.error} retry={history.refetch} />)}
    {tab === "Configuración fiscal" && <section className="panel commercial-inset"><p>NIT: {row.tax_id || "Sin registrar"}</p>
      <p>{row.plan.fel_enabled ? "El contrato admite FEL. Digifact está previsto para Fase 7."
        : "El contrato actual tiene FEL deshabilitada."}</p></section>}
    {tab === "Actividad" && (history.data ? <Table rows={history.data.activity} rowKey={(item) => item.id} columns={[
      { label: "Fecha", cell: (item) => formatDate(item.created_at) },
      { label: "Acción", cell: (item) => item.action }, { label: "Resultado", cell: (item) => item.result },
    ]} /> : <Load error={history.error} retry={history.refetch} />)}
    {invite && <Modal title="Invitar usuario" close={() => setInvite(false)}>
      <form onSubmit={(event) => {
        const data = entries(event);
        invitation.mutate({ path: `${path}/invitations`, body: Object.fromEntries(data) });
      }}>
        <Fields fields={[required("name", "Nombre"), required("email", "Correo electrónico", "email"),
          { ...required("role", "Rol", "select"), items: team.data?.roles.map((role) => ({ value: role.code, label: role.name })) }]} />
        {panelError(invitation.error)}<Save pending={invitation.isPending}>Enviar invitación</Save>
      </form>
    </Modal>}
    {selected && <SubscriptionInspect selected={selected} close={() => setSelected(null)} />}
  </>;
}


