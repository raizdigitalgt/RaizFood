"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2, Check, ChevronLeft, ChevronRight, CircleCheck, CreditCard, LayoutGrid, Plus,
  Search, ShieldCheck, Store, UserPlus, UsersRound, X,
} from "lucide-react";
import Link from "next/link";
import { useDeferredValue, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Field, Message } from "@/components/auth";
import { Button } from "@/components/ui/button";
import {
  ApiError, api, date, money, type Member, type Plan, type PlatformDashboard,
  type Restaurant, type RestaurantPage, type Role, type Team,
} from "@/lib/api";

function message(error: unknown) {
  return error instanceof ApiError ? error.message : "No se pudo conectar. Intenta nuevamente.";
}

function Status({ active }: { active: boolean }) {
  return <span className={`status ${active ? "status-active" : ""}`}><i />
    {active ? "Activo" : "Inactivo"}</span>;
}

function Heading({ title, summary, action }: { title: string; summary: string; action?: ReactNode }) {
  return <div className="page-heading"><div><h1>{title}</h1><p>{summary}</p></div>{action}</div>;
}

function QueryState({ error, retry }: { error: Error | null; retry: () => void }) {
  if (!error) return <div role="status" aria-label="Cargando información" className="panel skeleton" />;
  return <div className="panel empty"><Message>{message(error)}</Message>
    <Button variant="outline" onClick={retry}>Reintentar</Button></div>;
}

function Metrics({ items }: { items: { label: string; value: number | string; icon: typeof Building2 }[] }) {
  return <div className="metrics">{items.map(({ label, value, icon: Icon }, index) =>
    <article className={`panel metric metric-${index}`} key={label}>
      <span className="metric-icon"><Icon size={20} /></span>
      <p>{label}</p><strong>{value}</strong>
    </article>
  )}</div>;
}

function RestaurantsTable({ rows, action }: {
  rows: Restaurant[]; action?: (restaurant: Restaurant) => ReactNode;
}) {
  if (!rows.length) return <div className="empty"><Store size={27} /><p>No hay restaurantes para mostrar.</p></div>;
  return <div className="table-scroll"><table>
    <thead><tr><th>Restaurante</th><th>Plan</th><th>Usuarios</th><th>Estado</th><th>Alta</th>{action && <th>Acciones</th>}</tr></thead>
    <tbody>{rows.map((row) => <tr key={row.slug}>
      <td><div className="table-name"><span className="table-icon"><Store size={17} /></span>
        <span><strong><Link className="text-link" href={`/platform/restaurants/${row.slug}`}>{row.name}</Link></strong><small>{row.slug}</small></span></div></td>
      <td><span className={`plan-tag ${row.plan.fel_enabled ? "plan-pro" : ""}`}>{row.plan.name}</span></td>
      <td>{row.usage.total} / {row.plan.max_total}</td><td><Status active={row.active} /></td>
      <td>{date(row.created_at)}</td>{action && <td>{action(row)}</td>}
    </tr>)}</tbody>
  </table></div>;
}

function Meter({ label, value, max }: { label: string; value: number; max: number }) {
  return <div className="meter" role="progressbar" aria-label={label}
    aria-valuemin={0} aria-valuemax={max || 1} aria-valuenow={value} aria-valuetext={`${value} de ${max}`}>
    <span style={{ width: `${max ? Math.min(100, (value / max) * 100) : 0}%` }} />
  </div>;
}

export function PlatformOverview({ name }: { name: string }) {
  const { data, error, refetch } = useQuery({
    queryKey: ["platform-dashboard"], queryFn: () => api<PlatformDashboard>("/platform/dashboard"),
  });
  return <>
    <Heading title="Resumen de plataforma" summary={`Hola, ${name}. Consulta la actividad de Raíz Food.`}
      action={<Button asChild><Link href="/platform/restaurants"><Building2 size={17} /> Gestionar restaurantes</Link></Button>} />
    {data ? <>
      <Metrics items={[
        { label: "Restaurantes registrados", value: data.restaurants, icon: Building2 },
        { label: "Restaurantes activos", value: data.active, icon: CircleCheck },
        { label: "Usuarios activos", value: data.users, icon: UsersRound },
        { label: "Planes disponibles", value: data.plans, icon: CreditCard },
      ]} />
      <div className="bento">
        <section className="panel"><div className="panel-heading"><div><h2>Restaurantes recientes</h2>
          <p>Últimos establecimientos registrados.</p></div>
          <Link className="text-link" href="/platform/restaurants">Ver todos</Link></div>
          <RestaurantsTable rows={data.recent} />
        </section>
        <section className="panel"><div className="panel-heading"><div><h2>Estado de restaurantes</h2>
          <p>Distribución del total registrado.</p></div><span className="metric-icon"><LayoutGrid size={19} /></span></div>
          <div className="health-inner">
            <Meter label="Restaurantes activos" value={data.active} max={data.restaurants} />
            <div className="legend"><span><i /> Activos</span><strong>{data.active}</strong></div>
            <div className="legend inactive"><span><i /> Inactivos</span><strong>{data.restaurants - data.active}</strong></div>
          </div>
        </section>
      </div>
    </> : <QueryState error={error} retry={refetch} />}
  </>;
}

export function RestaurantOverview({ slug }: { slug: string }) {
  const { data, error, refetch } = useQuery({
    queryKey: ["restaurant", slug], queryFn: () => api<Restaurant>(`/restaurants/${slug}/dashboard`),
  });
  if (!data) return <QueryState error={error} retry={refetch} />;
  return <>
    <Heading title={data.name} summary="Resumen de tu restaurante." action={<Status active={data.active} />} />
    <Metrics items={[
      { label: "Plan contratado", value: data.plan.name, icon: CreditCard },
      { label: "Usuarios activos", value: data.usage.total, icon: UsersRound },
      { label: "Cupos disponibles", value: data.plan.max_total - data.usage.total, icon: CircleCheck },
    ]} />
    <section className="panel seat-panel"><div className="panel-heading"><div><h2>Capacidad del equipo</h2>
      <p>Cupos utilizados en el plan {data.plan.name}.</p></div><span className="metric-icon"><UsersRound size={19} /></span></div>
      <div className="health-inner">
        {[
          { label: "Administradores", value: data.usage.admins, max: data.plan.max_admins },
          { label: "Usuarios operativos", value: data.usage.staff, max: data.plan.max_staff },
        ].map(({ label, value, max }) => <div className="seat-row" key={label}>
          <div className="legend"><span>{label}</span><strong>{value} / {max}</strong></div>
          <Meter label={label} value={value} max={max} />
        </div>)}
      </div>
    </section>
  </>;
}

function usePlans() {
  return useQuery({ queryKey: ["plans"], queryFn: () => api<Plan[]>("/platform/plans") });
}

export function Plans() {
  const { data, error, refetch } = usePlans();
  return <>
    <Heading title="Planes" summary="Precios y cupos de los planes disponibles." />
    {data ? <div className="plan-grid">{data.map((plan) => <article key={plan.code} className="panel plan-card">
      <span className="metric-icon"><CreditCard size={20} /></span>
      <h2>{plan.name}</h2><p className="plan-price">{money(plan.monthly_cents)} <small>/ mes</small></p>
      <ul>
        <li><Check size={16} /> {plan.max_total} usuarios activos</li>
        <li><Check size={16} /> {plan.max_admins} administradores</li>
        <li><Check size={16} /> {plan.max_staff} usuarios operativos</li>
        <li><ShieldCheck size={16} /> {plan.fel_enabled ? "Plan con FEL" : "Plan sin FEL integrada"}</li>
      </ul>
    </article>)}</div> : <QueryState error={error} retry={refetch} />}
  </>;
}

function Modal({ title, children, close }: { title: string; children: ReactNode; close: () => void }) {
  return <dialog className="modal panel" ref={(node) => { if (node && !node.open) node.showModal(); }}
    aria-label={title} onCancel={close} onClose={close}>
    <div className="modal-header"><h2>{title}</h2>
      <button className="icon-button" type="button" onClick={close} aria-label="Cerrar"><X size={20} /></button>
    </div>{children}
  </dialog>;
}

const restaurantSchema = z.object({
  name: z.string().trim().min(2, "Ingresa al menos 2 caracteres.").max(100),
  slug: z.string().min(2, "Ingresa al menos 2 caracteres.").max(64)
    .regex(/^[a-z0-9]+(-[a-z0-9]+)*$/, "Usa minúsculas, números y guiones."),
  plan_code: z.string().min(1, "Selecciona un plan."),
});

function RestaurantForm({ close, done }: { close: () => void; done: (name: string) => void }) {
  const plans = usePlans();
  const { register, handleSubmit, formState: { errors } } = useForm<z.infer<typeof restaurantSchema>>({
    resolver: zodResolver(restaurantSchema),
  });
  const create = useMutation({
    mutationFn: (data: z.infer<typeof restaurantSchema>) =>
      api<Restaurant>("/platform/restaurants", { method: "POST", body: JSON.stringify(data) }),
    onSuccess: (restaurant) => done(restaurant.name),
  });
  return <Modal title="Registrar restaurante" close={close}>
    <form onSubmit={handleSubmit((values) => create.mutate(values))} noValidate>
      {(create.error || plans.error) && <Message>{message(create.error || plans.error)}</Message>}
      <Field label="Nombre comercial" error={errors.name?.message}><input autoFocus {...register("name")} /></Field>
      <Field label="Identificador" error={errors.slug?.message}>
        <input placeholder="ejemplo-restaurante" {...register("slug")} />
      </Field>
      <Field label="Plan" error={errors.plan_code?.message}><select {...register("plan_code")}>
        <option value="">Seleccionar plan</option>{plans.data?.map((plan) =>
          <option key={plan.code} value={plan.code}>{plan.name} · {money(plan.monthly_cents)}</option>)}
      </select></Field>
      <Button type="submit" disabled={create.isPending || !plans.data?.length} className="fill">
        {create.isPending ? "Registrando…" : "Registrar restaurante"}
      </Button>
    </form>
  </Modal>;
}

const roles: Role[] = [
  { code: "admin", name: "Administrador" }, { code: "cashier", name: "Cajero" },
  { code: "waiter", name: "Mesero" }, { code: "cook", name: "Cocinero" },
  { code: "inventory", name: "Encargado de inventario" },
];
const memberSchema = z.object({
  email: z.email("Ingresa un correo válido."),
  name: z.string().trim().max(100),
  password: z.string().max(128),
  role_code: z.string().min(1, "Selecciona un rol."),
});

export function MemberForm({ endpoint, choices, existingAllowed, close, done }: {
  endpoint: string; choices: Role[]; existingAllowed?: boolean; close: () => void; done: (name: string) => void;
}) {
  const [existing, setExisting] = useState(false);
  const { register, handleSubmit, setError, formState: { errors } } = useForm<z.infer<typeof memberSchema>>({
    resolver: zodResolver(memberSchema),
    defaultValues: { name: "", email: "", password: "", role_code: "" },
  });
  const create = useMutation({
    mutationFn: (data: z.infer<typeof memberSchema>) => api<Member>(endpoint, { method: "POST",
      body: JSON.stringify(existing ? { email: data.email, role_code: data.role_code } : data) }),
    onSuccess: (member) => done(member.name),
  });
  const submit = handleSubmit((values) => {
    if (!existing && (values.name.length < 2 || values.password.length < 12)) {
      if (values.name.length < 2) setError("name", { message: "Ingresa al menos 2 caracteres." });
      if (values.password.length < 12) setError("password", { message: "Usa al menos 12 caracteres." });
      return;
    }
    create.mutate(values);
  });
  return <Modal title="Agregar usuario" close={close}>
    <form onSubmit={submit} noValidate>
      {create.error && <Message>{message(create.error)}</Message>}
      {existingAllowed && <label className="check"><input type="checkbox" checked={existing}
        onChange={(event) => setExisting(event.target.checked)} /> Asociar una cuenta existente</label>}
      <Field label="Correo electrónico" error={errors.email?.message}>
        <input autoFocus type="email" autoComplete="off" {...register("email")} />
      </Field>
      {!existing && <>
        <Field label="Nombre" error={errors.name?.message}><input {...register("name")} /></Field>
        <Field label="Contraseña inicial" error={errors.password?.message}>
          <input type="password" autoComplete="new-password" {...register("password")} />
        </Field>
      </>}
      <Field label="Rol" error={errors.role_code?.message}><select {...register("role_code")}>
        <option value="">Seleccionar rol</option>{choices.map((role) =>
          <option key={role.code} value={role.code}>{role.name}</option>)}
      </select></Field>
      <Button type="submit" disabled={create.isPending} className="fill">
        {create.isPending ? "Guardando…" : "Agregar usuario"}
      </Button>
    </form>
  </Modal>;
}

function Notice({ text }: { text: string }) {
  return text && <div className="success-message" role="status"><Check size={17} />{text}</div>;
}

export function Restaurants({ open = false }: { open?: boolean }) {
  const [query, setQuery] = useState("");
  const [state, setState] = useState("");
  const [planCode, setPlanCode] = useState("");
  const [page, setPage] = useState(1);
  const [newRestaurant, setNewRestaurant] = useState(open);
  const [member, setMember] = useState<Restaurant | null>(null);
  const [notice, setNotice] = useState("");
  const deferred = useDeferredValue(query);
  const cache = useQueryClient();
  const { data, error, refetch } = useQuery({
    queryKey: ["restaurants", deferred, page, state, planCode],
    queryFn: () => api<RestaurantPage>(`/platform/restaurants?${new URLSearchParams({ q: deferred, page: String(page), state, plan_code: planCode })}`),
  });
  function changed(text: string) {
    setNotice(text);
    setNewRestaurant(false);
    setMember(null);
    void cache.invalidateQueries({ queryKey: ["restaurants"] });
    void cache.invalidateQueries({ queryKey: ["platform-dashboard"] });
  }
  return <>
    <Heading title="Restaurantes" summary="Consulta establecimientos y asigna acceso a sus equipos."
      action={<Button onClick={() => { setNotice(""); setNewRestaurant(true); }}><Plus size={18} /> Nuevo restaurante</Button>} />
    <Notice text={notice} />
    <section className="panel"><div className="panel-heading search-heading">
      <div><h2>Directorio</h2><p>{data ? `${data.total} resultados` : "Restaurantes registrados"}</p></div>
      <div className="search"><Search size={17} /><input type="search" aria-label="Buscar restaurantes"
        placeholder="Buscar restaurante" value={query} maxLength={100}
        onChange={(event) => { setQuery(event.target.value); setPage(1); }} /></div>
    </div>
      <div className="commercial-filters">
        <label>Estado<select value={state} onChange={(event) => { setState(event.target.value); setPage(1); }}>
          <option value="">Todos</option><option value="active">Activos</option><option value="suspended">Suspendidos</option>
        </select></label>
        <label>Código de plan<input value={planCode} onChange={(event) => { setPlanCode(event.target.value); setPage(1); }} /></label>
      </div>
      {data ? <>
        <RestaurantsTable rows={data.items} action={(row) => row.active &&
          <Button variant="ghost" aria-label={`Agregar usuario a ${row.name}`} onClick={() => {
            setNotice(""); setMember(row);
          }}><UserPlus size={17} /> Agregar usuario</Button>} />
        <div className="pagination"><span>Página {page} de {Math.max(1, Math.ceil(data.total / 12))}</span>
          <Button variant="outline" disabled={page === 1} aria-label="Página anterior" onClick={() => setPage(page - 1)}><ChevronLeft size={17} /></Button>
          <Button variant="outline" disabled={page * 12 >= data.total} aria-label="Página siguiente" onClick={() => setPage(page + 1)}><ChevronRight size={17} /></Button>
        </div>
      </> : <QueryState error={error} retry={refetch} />}
    </section>
    {newRestaurant && <RestaurantForm close={() => setNewRestaurant(false)}
      done={(name) => { setQuery(""); setPage(1); changed(`${name} se registró correctamente.`); }} />}
    {member && <MemberForm endpoint={`/platform/restaurants/${member.slug}/members`} choices={roles} existingAllowed
      close={() => setMember(null)} done={(name) => changed(`${name} se agregó a ${member.name}.`)} />}
  </>;
}

export function TeamView({ slug }: { slug: string }) {
  const [open, setOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const cache = useQueryClient();
  const endpoint = `/restaurants/${slug}/members`;
  const { data, error, refetch } = useQuery({ queryKey: ["team", slug], queryFn: () => api<Team>(endpoint) });
  return <>
    <Heading title="Equipo" summary="Consulta los usuarios y roles de tu restaurante."
      action={data && <Button onClick={() => { setNotice(""); setOpen(true); }}><UserPlus size={18} /> Agregar usuario</Button>} />
    <Notice text={notice} />
    {data ? <section className="panel"><div className="panel-heading"><div><h2>Miembros</h2><p>{data.items.length} usuarios</p></div></div>
      <div className="table-scroll"><table><thead><tr><th>Nombre</th><th>Correo</th><th>Rol</th><th>Estado</th></tr></thead>
        <tbody>{data.items.map((row) => <tr key={row.email}><td><strong>{row.name}</strong></td>
          <td>{row.email}</td><td>{row.role}</td><td><Status active={row.active} /></td></tr>)}</tbody>
      </table></div>
    </section> : <QueryState error={error} retry={refetch} />}
    {open && data && <MemberForm endpoint={endpoint} choices={data.roles} close={() => setOpen(false)}
      done={(name) => {
        setOpen(false); setNotice(`${name} se agregó al equipo.`);
        void cache.invalidateQueries({ queryKey: ["team", slug] });
        void cache.invalidateQueries({ queryKey: ["restaurant", slug] });
      }} />}
  </>;
}
