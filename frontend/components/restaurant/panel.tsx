"use client";

import { BookOpen, CalendarClock, ClipboardList, CookingPot, Images, Settings, UserPlus, UsersRound, Armchair, LayoutList } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { OperationalMetrics } from "@/components/pos/operations";
import { money, type Restaurant as BaseRestaurant } from "@/lib/api";
import { restaurantRights } from "@/lib/restaurant-nav";
import {
  day, Fields, formatDate, Heading, label, Load, Modal, Note, panelError, Pill,
  queryString, Save, Table, useChange, useData, type FormField,
} from "@/components/platform/shared";
import {
  apiRoot, checkbox, choices, enumerated, formData, options, Pager, parseFields,
  Photo, PhotoPicker, required, resourcePath, Seats, Segments, type Entry, type Count, type Limits, type PageData,
} from "./shared";

type SubscriptionInfo = { id: string; plan: string; starts_on: string; ends_on: string; state: string;
  remaining_days: number; price_cents: number; discount_cents: number; cycle: string };
type Plan = Limits & { name: string; code: string; monthly_cents: number; fel_enabled: boolean; features: string[] };
type Audit = { id: string; user: string; action: string; subject: string; created_at: number; result: string; detail: string };
type OverviewData = BaseRestaurant & { counts: Record<string, number>; subscription: SubscriptionInfo | null; activity: Audit[] };

const shortcuts = [
  ["pos?new=1", "Nuevo pedido", ClipboardList, ["orders.create"]],
  ["tables", "Consultar mesas", Armchair, ["tables.view"]],
  ["orders", "Consultar pedidos", ClipboardList, ["orders.view"]],
  ["kitchen", "Abrir cocina", CookingPot, ["kitchen.view"]],
  ["menu?new=1", "Agregar platillo", BookOpen, ["menu.manage", "menu.create"]],
  ["categories?new=1", "Crear categoría", LayoutList, ["menu.manage", "categories.create"]],
  ["tables?new=1", "Crear mesa", Armchair, ["tables.manage"]],
  ["customers?new=1", "Registrar cliente", UsersRound, ["customers.manage", "customers.create"]],
  ["team?invite=1", "Invitar usuario", UserPlus, ["users.manage", "users.invite"]],
  ["media?new=1", "Subir fotografía", Images, ["media.manage"]],
  ["subscription", "Consultar suscripción", CalendarClock, ["subscription.view"]],
  ["settings", "Configurar restaurante", Settings, ["settings.manage"]],
] as const;

export function RestaurantDashboard({ slug, permissions, name }: { slug: string; permissions: string[]; name: string }) {
  const query = useData<OverviewData>(`${apiRoot(slug)}/overview`);
  const appearance = useData<{ cover_id: string | null }>(`${apiRoot(slug)}/appearance`);
  const data = query.data;
  const stats = data ? [
    ["Platillos registrados", data.counts.items, BookOpen],
    ["Disponibles", data.counts.available, CookingPot],
    ["Platillos inactivos", data.counts.inactive, BookOpen],
    ["Categorías", data.counts.categories, LayoutList],
    ["Mesas registradas", data.counts.tables, Armchair], ["Áreas", data.counts.areas, Armchair],
    ["Clientes registrados", data.counts.customers, UsersRound],
    ["Usuarios activos", data.usage.total, UsersRound],
  ] as const : [];
  return <>
    <Heading title={data?.name ?? name} text="Resumen del restaurante y accesos a su administración." />
    {appearance.data?.cover_id && <div className="panel restaurant-cover export-actions">
      <Photo slug={slug} id={appearance.data.cover_id} alt="Imagen comercial del restaurante" />
    </div>}
    <section className="panel quick-links"><h2>Accesos rápidos</h2><div className="commercial-actions">
      {shortcuts.filter(([, , , scopes]) => restaurantRights(permissions, ...scopes)).map(([href, title, Icon]) =>
        <Button key={href} asChild variant="outline"><Link href={`/app/${slug}/${href}`}><Icon size={17} /> {title}</Link></Button>)}
    </div></section>
    {permissions.includes("reports.operational") && <OperationalMetrics slug={slug} />}
    {data ? <>
      <section className="metrics overview-metrics" aria-label="Indicadores del restaurante">
        {stats.map(([title, count, Icon], index) => <article key={title} className={`panel metric metric-${index % 4}`}>
          <span className="metric-icon"><Icon size={19} /></span><p>{title}</p><strong>{count}</strong>
        </article>)}
      </section>
      <div className="commercial-chart-grid">
        <section className="panel commercial-inset"><h2>Cupos del equipo</h2><Seats used={data.usage} limits={data.plan} /></section>
        {permissions.includes("subscription.view") && <section className="panel commercial-inset commercial-stack">
          <div className="commercial-row"><h2>{data.plan.name}</h2><Pill value={data.subscription?.state ?? "Asignación inicial"} /></div>
          <p>{data.subscription ? `Vencimiento: ${day(data.subscription.ends_on)}` : "El restaurante aún no tiene una fecha de vencimiento."}</p>
        </section>}
      </div>
      {permissions.includes("audit.view") && <div className="commercial-stack export-actions">
        <h2>Actividad reciente</h2><AuditTable rows={data.activity} brief />
      </div>}
    </> : <Load error={query.error} retry={query.refetch} />}
   </>;
}

type SettingsData = Record<string, unknown> & { name: string; logo_id: string | null; cover_id: string | null; days: string[]; order_modes: string[] };
const tabs = ["Información general", "Personalización", "Operación", "Comercial", "Fiscal", "Impresión"];
const fields: Record<string, FormField[]> = {
  "Información general": [
    required("name", "Nombre comercial"), { name: "legal_name", label: "Razón social" }, { name: "tax_id", label: "NIT" },
    { name: "address", label: "Dirección", type: "textarea" }, { name: "department", label: "Departamento" },
    { name: "municipality", label: "Municipio" }, { name: "phone", label: "Teléfono" },
    { name: "contact_email", label: "Correo electrónico", type: "email" }, { name: "owner", label: "Propietario" },
    { name: "contact_info", label: "Información de contacto" },
  ],
  Personalización: [{ name: "display_name", label: "Nombre visible" }, { name: "accent", label: "Color de acento hexadecimal",
    hint: "Ejemplo #EA580C. Déjalo vacío para usar el tema predeterminado." }],
  Operación: [{ name: "hours", label: "Horario de atención", type: "textarea" },
    { name: "table_policy", label: "Configuración de mesas", type: "textarea" }, checkbox("default_available", "Platillos disponibles por defecto")],
  Comercial: [options("currency", "Moneda", [{ value: "GTQ", label: "Quetzal guatemalteco (GTQ)" }]),
    { name: "discount_policy", label: "Política de descuentos", type: "textarea" },
    { name: "thanks", label: "Mensaje de agradecimiento", type: "textarea" },
    { name: "receipt_preferences", label: "Preferencias de comprobantes", type: "textarea" }],
  Fiscal: [{ name: "legal_name", label: "Razón social" }, { name: "tax_id", label: "NIT" },
    { name: "address", label: "Dirección fiscal", type: "textarea" }],
};
const dayOptions = { lun: "Lunes", mar: "Martes", mié: "Miércoles", jue: "Jueves", vie: "Viernes", sáb: "Sábado", dom: "Domingo" };
const orderOptions = { dine_in: "En el restaurante", takeaway: "Para llevar", delivery: "Entrega" };
const regionTimezones = ["America/Guatemala", "America/Belize", "America/El_Salvador", "America/Tegucigalpa",
  "America/Costa_Rica", "America/Managua", "America/Panama", "America/Mexico_City"];

function multi(name: string, title: string, values: Record<string, string>, selected: string[]) {
  return <fieldset className="restaurant-fieldset"><legend>{title}</legend><div className="commercial-fields">
    {enumerated(values).map((option) => <label className="check" key={option.value}><input type="checkbox" name={name}
      value={option.value} defaultChecked={selected.includes(option.value)} />{option.label}</label>)}
  </div></fieldset>;
}

function SettingsForm({ slug, data, tab, canMedia }: { slug: string; data: SettingsData; tab: string; canMedia: boolean }) {
  const router = useRouter();
  const [logo, setLogo] = useState(data.logo_id ?? "");
  const [cover, setCover] = useState(data.cover_id ?? "");
  const [notice, setNotice] = useState("");
  const operations = tab === "Operación";
  const areas = useData<PageData<Entry>>(resourcePath(slug, "areas") + "?size=100&active=true", operations);
  const preparation = useData<PageData<Entry>>(resourcePath(slug, "preparation") + "?size=100&active=true", operations);
  const change = useChange(() => { setNotice("Configuración guardada."); router.refresh(); });
  const form = [...(fields[tab] ?? [])];
  if (operations) form.push(
    options("timezone", "Zona horaria", regionTimezones.map((value) => ({ value, label: value }))),
    options("default_area_id", "Área de atención predeterminada", choices(areas.data?.items), false),
    options("default_preparation_id", "Área de preparación predeterminada", choices(preparation.data?.items), false),
  );
  return <form className="panel commercial-inset" onSubmit={(event) => {
    const entries = formData(event);
    change.mutate({ path: `${apiRoot(slug)}/settings`, method: "PUT", body: {
      ...data, ...parseFields(form, entries), ...(operations ? {
        days: entries.getAll("days"), order_modes: entries.getAll("order_modes"),
      } : {}), ...(tab === "Personalización" ? { logo_id: logo || null, cover_id: cover || null } : {}),
    } });
  }}>
    {tab === "Fiscal" && <p>La emisión FEL mediante Digifact está prevista para la Fase 7.</p>}
    <Note>{notice}</Note>
    <Fields fields={form} initial={data} />
    {operations && <>{multi("days", "Días de funcionamiento", dayOptions, data.days)}
      {multi("order_modes", "Modalidades de pedido", orderOptions, data.order_modes)}</>}
    {tab === "Personalización" && <div className="commercial-chart-grid">
      <PhotoPicker slug={slug} title="Logotipo del restaurante" selected={logo} change={setLogo} allowed={canMedia} />
      <PhotoPicker slug={slug} title="Imagen comercial" selected={cover} change={setCover} allowed={canMedia} />
    </div>}
    {panelError(change.error || areas.error || preparation.error)}<Save pending={change.isPending} />
  </form>;
}

export function RestaurantSettings({ slug, permissions }: { slug: string; permissions: string[] }) {
  const query = useData<SettingsData>(`${apiRoot(slug)}/settings`);
  const [tab, setTab] = useState(tabs[0]);
  return <>
    <Heading title="Configuración del restaurante" text="Ajusta la identidad y las preferencias operativas del establecimiento." />
    <Segments label="Configuración" values={tabs} selected={tab} change={setTab} />
    {tab === "Impresión" ? <section className="panel commercial-inset"><h2>Impresión térmica</h2>
      <p>La configuración de impresoras y el agente de impresión se incorporarán en la Fase 5.</p></section>
      : query.data ? <SettingsForm key={tab} slug={slug} data={query.data} tab={tab} canMedia={permissions.includes("media.manage")} />
        : <Load error={query.error} retry={query.refetch} />}
    {tab === "Operación" && <div className="commercial-actions settings-links">
      <Button asChild variant="outline"><Link href={`/app/${slug}/pos-settings`}>Configurar punto de venta</Link></Button>
      <Button asChild variant="outline"><Link href={`/app/${slug}/preparation`}>Áreas de preparación</Link></Button>
      {permissions.includes("tables.view") && <Button asChild variant="outline"><Link href={`/app/${slug}/areas`}>Áreas y salones</Link></Button>}
    </div>}
    {tab === "Comercial" && <div className="settings-links"><Button asChild variant="outline">
      <Link href={`/app/${slug}/payment-methods`}>Administrar métodos de pago</Link></Button></div>}
  </>;
}

type SubscriptionData = { plan: Plan; subscription: SubscriptionInfo | null; usage: Count; plans: Plan[];
  history: { id: string; action: string; snapshot: { state: string; ends_on: string }; created_at: number }[];
  payments: { id: string; amount_cents: number; state: string; method: string; paid_on: string; reference: string; starts_on: string; ends_on: string }[];
  requests: { id: string; notes: string; status: string; created_at: number }[] };
function PlanRequest({ slug, plans, close, done }: { slug: string; plans: Plan[]; close: () => void; done: () => void }) {
  const change = useChange(done);
  return <Modal title="Solicitar cambio de plan" close={close}>
    <form onSubmit={(event) => change.mutate({ path: `${apiRoot(slug)}/subscription/requests`,
      body: Object.fromEntries(formData(event)) })}>
      <Fields fields={[options("plan_code", "Plan solicitado", plans.map((item) => ({ value: item.code, label: item.name }))),
        { name: "notes", label: "Mensaje para Raíz Digital", type: "textarea" }]} />
      {panelError(change.error)}<Save pending={change.isPending}>Enviar solicitud</Save>
    </form>
  </Modal>;
}

export function SubscriptionView({ slug }: { slug: string }) {
  const query = useData<SubscriptionData>(`${apiRoot(slug)}/subscription`);
  const [modal, setModal] = useState(false);
  const [notice, setNotice] = useState("");
  const change = useChange(() => setNotice("Solicitud cancelada."));
  if (!query.data) return <Load error={query.error} retry={query.refetch} />;
  const { plan, subscription, plans, usage, payments, history, requests } = query.data;
  const pending = requests.find((item) => item.status === "pending");
  const alternatives = plans.filter((item) => item.code !== plan.code);
  return <>
    <Heading title="Mi suscripción" text="Consulta tu plan, sus condiciones y el historial comercial."
      action={Boolean(alternatives.length) && !pending && <Button onClick={() => setModal(true)}>Solicitar cambio de plan</Button>} />
    <Note>{notice}</Note>{panelError(change.error)}
    {pending && <section className="panel commercial-inset commercial-row export-actions"><p>Solicitud de cambio pendiente · {formatDate(pending.created_at)}</p>
      <Button variant="outline" disabled={change.isPending} onClick={() => {
        if (window.confirm("¿Cancelar esta solicitud?")) change.mutate({
          path: `${apiRoot(slug)}/subscription/requests/${pending.id}`, method: "DELETE",
        });
      }}>Cancelar solicitud</Button></section>}
    <div className="commercial-chart-grid">
      <section className="panel commercial-inset commercial-stack">
        <div className="commercial-row"><h2>{plan.name}</h2><Pill value={subscription?.state ?? "Asignación inicial"} /></div>
        <strong>{money(subscription ? subscription.price_cents - subscription.discount_cents : plan.monthly_cents)}
          {subscription ? ` · ${label(subscription.cycle)}` : " · Mensual"}</strong>
        {subscription && <p>Inicio {day(subscription.starts_on)} · Vencimiento {day(subscription.ends_on)} · {subscription.remaining_days} días</p>}
        {plan.features.length > 0 && <p>{plan.features.join(" · ")}</p>}
      </section>
      <section className="panel commercial-inset"><h2>Cupos contratados</h2><Seats used={usage} limits={plan} /></section>
    </div>
    <section className="commercial-stack export-actions">
      <h2>Planes vigentes</h2><Table rows={plans} rowKey={(item) => item.code} columns={[
        { label: "Plan", cell: (item) => item.name }, { label: "Mensual", cell: (item) => money(item.monthly_cents) },
        { label: "Adm. / Operativos / Total", cell: (item) => `${item.max_admins} / ${item.max_staff} / ${item.max_total}` },
        { label: "FEL", cell: (item) => item.fel_enabled ? "Habilitada por plan" : "Deshabilitada por plan" },
      ]} />
      <h2>Pagos</h2><Table rows={payments} rowKey={(item) => item.id}
        columns={[{ label: "Fecha", cell: (item) => day(item.paid_on) }, { label: "Monto", cell: (item) => money(item.amount_cents) },
          { label: "Método", cell: (item) => item.method }, { label: "Estado", cell: (item) => <Pill value={item.state} /> }]} />
      <h2>Historial de renovaciones y cambios</h2><Table rows={history} rowKey={(item) => item.id}
        columns={[{ label: "Fecha", cell: (item) => formatDate(item.created_at) }, { label: "Acción", cell: (item) => item.action },
          { label: "Vencimiento", cell: (item) => day(item.snapshot.ends_on) }, { label: "Estado", cell: (item) => <Pill value={item.snapshot.state} /> }]} />
    </section>
    {modal && <PlanRequest slug={slug} plans={alternatives} close={() => setModal(false)}
      done={() => { setModal(false); setNotice("Solicitud enviada a Raíz Digital."); }} />}
  </>;
}

function AuditTable({ rows, brief = false }: { rows: Audit[]; brief?: boolean }) {
  return <Table rows={rows} rowKey={(item) => item.id} columns={[
    { label: "Fecha", cell: (item) => new Intl.DateTimeFormat("es-GT", {
      dateStyle: "short", timeStyle: "short", timeZone: "America/Guatemala",
    }).format(item.created_at * 1000) },
    { label: "Usuario", cell: (item) => item.user }, { label: "Acción", cell: (item) => item.action },
    ...(!brief ? [{ label: "Entidad", cell: (item: Audit) => item.subject },
      { label: "Resultado", cell: (item: Audit) => item.result },
      { label: "Detalles", cell: (item: Audit) => item.detail || "—" }] : []),
  ]} />;
}
export function RestaurantAudit({ slug }: { slug: string }) {
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [page, setPage] = useState(1);
  const query = useData<PageData<Audit>>(`${apiRoot(slug)}/audit?${queryString({ ...filters, page: String(page) })}`);
  return <>
    <Heading title="Auditoría del restaurante" text="Consulta los cambios registrados dentro del restaurante actual." />
    <form className="panel commercial-inset export-actions" onSubmit={(event) => {
      const body = formData(event);
      const timestamp = (name: string, hour: string) => body.get(name)
        ? String(Date.parse(`${body.get(name)}T${hour}-06:00`) / 1000) : "";
      setPage(1); setFilters({ q: String(body.get("q")), action: String(body.get("action")),
        start: timestamp("start", "00:00:00"), end: timestamp("end", "23:59:59") });
    }}>
      <Fields fields={[{ name: "q", label: "Buscar usuario, acción o entidad" },
        { name: "action", label: "Acción exacta" }, { name: "start", label: "Desde", type: "date" },
        { name: "end", label: "Hasta", type: "date" }]} />
      <Save pending={query.isFetching}>Filtrar</Save>
    </form>
    {query.data ? <><AuditTable rows={query.data.items} /><Pager total={query.data.total} page={page} setPage={setPage} /></>
      : <Load error={query.error} retry={query.refetch} />}
  </>;
}
