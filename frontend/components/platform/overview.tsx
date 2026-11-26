"use client";

import { Building2, CalendarClock, CircleCheck, CreditCard, DatabaseBackup, Plus, UsersRound, Wallet } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { money } from "@/lib/api";
import { day, formatDate, Heading, label, Load, Pill, queryString, Table, useData } from "./shared";

interface Summary {
  range: { start: string; end: string };
  restaurants: number; active_restaurants: number; suspended_restaurants: number; catalog_plans: number;
  recent_restaurants: { slug: string; name: string; created_at: number; active: boolean; plan: string }[];
  trial_restaurants: number; registered_users: number; subscription_states: Record<string, number>;
  expiring: number; monthly_recurring_cents: number; annual_projected_cents: number;
  collected_cents: number; outstanding_cents: number; received_month: number; pending_payments: number;
  basic_restaurants: number; pro_restaurants: number; plan_distribution: { plan: string; count: number }[];
  series: { month: string; income_cents: number; payments: number; restaurants: number }[];
  backup: { state: string; created_at: number } | null;
  activity: { id: string; action: string; created_at: number; result: string; user: string }[];
}
const quick = [
  ["restaurants", "Nuevo restaurante", Building2], ["payments", "Registrar pago", Wallet],
  ["subscriptions", "Nueva suscripción", CalendarClock], ["plans", "Crear plan", CreditCard],
  ["users", "Crear usuario", UsersRound], ["backups", "Generar respaldo", DatabaseBackup],
] as const;

export function Overview({ scopes, reports = false }: { scopes: string[]; reports?: boolean }) {
  const [range, setRange] = useState({ start: "", end: "" });
  const query = useData<Summary>(`/platform/${reports ? "reports" : "commercial-summary"}?${queryString(range)}`);
  const data = query.data;
  const metrics = data ? [
    ["Restaurantes", data.restaurants, Building2], ["Activos", data.active_restaurants, CircleCheck],
    ["Suspendidos", data.suspended_restaurants, Building2], ["En prueba", data.trial_restaurants, CalendarClock],
    ["Usuarios registrados", data.registered_users, UsersRound], ["Planes disponibles", data.catalog_plans, CreditCard],
    ["Plan Básico", data.basic_restaurants, CreditCard], ["Plan Pro", data.pro_restaurants, CreditCard],
    ["Suscripciones activas", data.subscription_states.active ?? 0, CircleCheck],
    ["Vencidas", data.subscription_states.expired ?? 0, CalendarClock], ["Próximas a vencer", data.expiring, CalendarClock],
    ["Ingreso recurrente mensual", money(data.monthly_recurring_cents), Wallet],
    ["Proyección anual", money(data.annual_projected_cents), CreditCard],
    ["Ingresos cobrados", money(data.collected_cents), Wallet],
    ["Saldo pendiente", money(data.outstanding_cents), Wallet],
    ["Pagos pendientes", data.pending_payments, Wallet],
    ["Pagos recibidos este mes", data.received_month, CircleCheck],
  ] as const : [];
  return <>
    <Heading title={reports ? "Reportes" : "Resumen de plataforma"}
      text={reports ? "Consulta los indicadores comerciales por fecha." : "Gestiona restaurantes, contratos y cobros de Raíz Food."}
      action={!reports && scopes.includes("restaurants") &&
        <Button asChild><Link href="/platform/restaurants"><Building2 size={17} /> Gestionar restaurantes</Link></Button>} />
    {!reports && <div className="panel quick-links">
      <h2>Accesos rápidos</h2><div className="commercial-actions">{quick.filter(([section]) => scopes.includes(section))
        .map(([section, caption, Icon]) => <Button key={section} variant="outline" asChild>
          <Link href={`/platform/${section}?new=1`}><Icon size={16} />{caption}</Link></Button>)}</div>
    </div>}
    <div className="commercial-filters panel">
      {(["start", "end"] as const).map((key) => <label key={key}>{key === "start" ? "Desde" : "Hasta"}
        <input type="date" value={range[key]} onChange={(event) => setRange({ ...range, [key]: event.target.value })} /></label>)}
      <Button variant="ghost" onClick={() => setRange({ start: "", end: "" })}>Mes actual</Button>
      {data && <p>Cobros y altas del {day(data.range.start)} al {day(data.range.end)}</p>}
    </div>
    {data ? <>
      <section className="metrics overview-metrics" aria-label="Indicadores">{metrics.map(([caption, value, Icon], index) =>
        <article key={caption} className={`panel metric metric-${index % 4}`}>
          <span className="metric-icon"><Icon size={19} /></span><p>{caption}</p><strong>{value}</strong>
        </article>)}</section>
      <div className="commercial-chart-grid">
        <Chart title="Ingresos mensuales" series={data.series} category="month" metric="income_cents" currency />
        <Chart title="Crecimiento de restaurantes" series={data.series} category="month" metric="restaurants" />
        <Chart title="Distribución de planes" series={data.plan_distribution} category="plan" metric="count" />
        <Chart title="Estado de suscripciones" series={Object.entries(data.subscription_states)
          .map(([state, count]) => ({ state: label(state), count }))} category="state" metric="count" />
        <Chart title="Pagos recibidos" series={data.series} category="month" metric="payments" />
        {scopes.includes("backups") && <section className="panel commercial-inset commercial-stack">
          <div className="commercial-row"><h2>Respaldos</h2><DatabaseBackup size={20} /></div>
          {data.backup ? <><Pill value={data.backup.state} /><p>{formatDate(data.backup.created_at)}</p></>
            : <p>Aún no hay respaldos registrados en el panel.</p>}
          <Button asChild variant="outline">
            <Link href="/platform/backups"><Plus size={16} /> Ver respaldos</Link></Button>
        </section>}
      </div>
      {scopes.includes("restaurants") && <div className="commercial-stack export-actions"><h2>Restaurantes recientes</h2>
        <Table rows={data.recent_restaurants} rowKey={(item) => item.slug} columns={[
          { label: "Restaurante", cell: (item) => <Link className="text-link" href={`/platform/restaurants/${item.slug}`}>{item.name}</Link> },
          { label: "Plan", cell: (item) => item.plan }, { label: "Fecha de alta", cell: (item) => formatDate(item.created_at) },
          { label: "Estado", cell: (item) => <Pill value={item.active ? "active" : "suspended"} /> },
        ]} /></div>}
      {scopes.includes("audit") && <div className="commercial-stack"><h2>Actividad reciente</h2>
        <Table rows={data.activity} rowKey={(item) => item.id} columns={[
          { label: "Acción", cell: (item) => item.action }, { label: "Usuario", cell: (item) => item.user },
          { label: "Fecha", cell: (item) => formatDate(item.created_at) }, { label: "Resultado", cell: (item) => label(item.result) },
        ]} /></div>}
    </> : <Load error={query.error} retry={query.refetch} />}
  </>;
}

function Chart({ title, series, category, metric, currency = false }: {
  title: string; series: Record<string, string | number>[]; category: string; metric: string; currency?: boolean;
}) {
  return <section className="panel commercial-chart">
    <h2>{title}</h2>
    {series.length ? <div className="chart-area" role="img" aria-label={title}>
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <BarChart data={series} margin={{ top: 8, right: 10, left: 0, bottom: 4 }}>
          <CartesianGrid stroke="var(--line)" vertical={false} />
          <XAxis dataKey={category} tick={{ fill: "var(--muted)", fontSize: 12 }} tickLine={false} />
          <YAxis width={currency ? 70 : 35} tickLine={false} allowDecimals={false}
            tick={{ fill: "var(--muted)", fontSize: 12 }}
            tickFormatter={(value) => currency ? money(value) : String(value)} />
          <Tooltip cursor={{ fill: "var(--surface-soft)" }} labelStyle={{ color: "var(--text)" }}
            contentStyle={{ background: "var(--sidebar)", border: "1px solid var(--line)", borderRadius: 8 }}
            formatter={(value) => [currency ? money(Number(value)) : value, title]} />
          <Bar dataKey={metric} fill="var(--primary)" radius={[4, 4, 0, 0]} maxBarSize={42} />
        </BarChart>
      </ResponsiveContainer>
    </div> : <div className="empty"><p>No hay datos en este período.</p></div>}
  </section>;
}
