"use client";

import Image from "next/image";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import type { Identity } from "@/lib/api";
import {
  entries, errorText, Fields, fileContent, formatDate, getText, Heading, label, lines, Load, Modal,
  NewButton, Note, panelError, Pill, queryString, Save, Table, useChange, useData, type FormField,
} from "./shared";

const required = (name: string, label: string, type?: FormField["type"]): FormField =>
  ({ name, label, type, required: true });
const select = (name: string, label: string, items: Record<string, string>): FormField =>
  ({ ...required(name, label, "select"), items: Object.entries(items).map(([value, label]) => ({ value, label })) });
const platformRoles: Record<string, string> = {
  super: "Superadministrador", admin: "Administrador de plataforma", commercial: "Encargado comercial",
  support: "Encargado de soporte", auditor: "Auditor",
};

interface Account { id: string; name: string; email: string; role: string; active: boolean }
interface Session { id: string; expires_at: number; revoked: boolean; mfa_verified: boolean }
interface AuditItem { id: string; action: string; subject: string; created_at: number; result: string;
  detail: string; user: string; restaurant: string | null }
interface SMTP {
  host?: string; port?: number; username?: string; sender_name?: string; sender_email?: string;
  security?: string; enabled: boolean; mode: string; has_password: boolean;
}
export interface Branding {
  name: string; support_email: string; contact: string; footer: string; primary: string; assets: string[];
}
interface Backup { id: string; filename: string; size: number; revision: string; state: string; created_at: number }
interface BackupPolicy { automatic: boolean; interval_hours: number; retention_days: number }
interface NoticeItem { id: string; kind: string; message: string; read: boolean; created_at: number }
interface Ticket { id: string; subject: string; description: string; priority: string; state: string;
  assignee_id: string | null; assignee: string | null; restaurant_name: string; created_at: number }
interface TicketDetail extends Ticket {
  history: { id: string; message: string; state: string; user: string; created_at: number }[];
}

function AccountForm({ mode, account, close, done }: {
  mode: "create" | "invite" | "edit"; account?: Account; close: () => void; done: (status?: string) => void;
}) {
  const change = useChange<{ status?: string }>((data) => done(data.status));
  const fields = [required("name", "Nombre"), select("role", "Rol", platformRoles)];
  if (mode !== "edit") fields.push(required("email", "Correo electrónico", "email"));
  if (mode === "create") fields.push({ ...required("password", "Contraseña inicial", "password"), hint: "Mínimo 12 caracteres." });
  if (mode === "edit") fields.push({ name: "active", label: "Usuario activo", type: "checkbox" });
  const title = { create: "Crear usuario", invite: "Invitar usuario", edit: "Editar usuario" }[mode];
  return <Modal title={title} close={close}><form onSubmit={(event) => {
    const data = entries(event);
    change.mutate({ path: mode === "edit" ? `/platform/users/${account?.id}` : mode === "invite"
      ? "/platform/users/invitations" : "/platform/users",
      method: mode === "edit" ? "PUT" : "POST",
      body: { ...Object.fromEntries(data), active: data.has("active") } });
  }}>
    <Fields fields={fields} initial={account ? { ...account } : { role: "support" }} />
    {panelError(change.error)}<Save pending={change.isPending}>{title}</Save>
  </form></Modal>;
}

function Sessions({ account, close }: { account: Account; close: () => void }) {
  const path = `/platform/users/${account.id}/sessions`;
  const query = useData<Session[]>(path);
  const change = useChange();
  return <Modal title={`Sesiones de ${account.name}`} close={close}>
    {panelError(change.error)}
    {query.data ? <Table rows={query.data} rowKey={(row) => row.id} columns={[
      { label: "Vencimiento", cell: (row) => formatDate(row.expires_at) },
      { label: "MFA", cell: (row) => row.mfa_verified ? "Verificado" : "Sin verificar" },
      { label: "Estado", cell: (row) => row.revoked ? "Revocada" : row.expires_at < Date.now() / 1000 ? "Vencida" : "Activa" },
      { label: "Acción", cell: (row) => !row.revoked && row.expires_at > Date.now() / 1000 &&
        <Button variant="ghost" disabled={change.isPending} onClick={() => {
          if (window.confirm("¿Revocar esta sesión?")) change.mutate({ path: `${path}/${row.id}/revoke` });
        }}>Revocar</Button> },
    ]} /> : <Load error={query.error} retry={query.refetch} />}
  </Modal>;
}

const editablePermissions: Record<string, string> = {
  dashboard: "Dashboard", restaurants: "Restaurantes", plans: "Planes", subscriptions: "Suscripciones",
  payments: "Pagos", audit: "Auditoría", settings: "Configuración", branding: "Personalización",
  backups: "Respaldos", notifications: "Notificaciones", support: "Soporte", fel: "FEL general", reports: "Reportes",
};

function Roles({ close }: { close: () => void }) {
  const query = useData<Record<string, string[]>>("/platform/roles");
  const [role, setRole] = useState("commercial");
  const [notice, setNotice] = useState("");
  const change = useChange(() => setNotice("Permisos actualizados."));
  return <Modal title="Permisos de plataforma" close={close}>
    <Note>{notice}</Note>
    <label className="field">Rol<select value={role} onChange={(event) => {
      setRole(event.target.value); setNotice(""); change.reset();
    }}>{Object.entries(platformRoles).filter(([value]) => value !== "super")
      .map(([value, title]) => <option key={value} value={value}>{title}</option>)}</select></label>
    {query.data ? <form key={role} onSubmit={(event) => {
      const data = entries(event);
      change.mutate({ path: `/platform/roles/${role}`, method: "PUT", body: { permissions: Array.from(data.keys()) } });
    }}>
      <Fields fields={Object.entries(editablePermissions).map(([name, label]) => ({ name, label, type: "checkbox" }))}
        initial={Object.fromEntries((query.data[role] ?? []).map((key) => [key, true]))} />
      {panelError(change.error)}<Save pending={change.isPending}>Guardar permisos</Save>
    </form> : <Load error={query.error} retry={query.refetch} />}
  </Modal>;
}

export function Users({ open }: { open: boolean }) {
  const query = useData<Account[]>("/platform/users");
  const [form, setForm] = useState<"create" | "invite" | Account | null>(open ? "create" : null);
  const [sessions, setSessions] = useState<Account | null>(null);
  const [roles, setRoles] = useState(false);
  const [notice, setNotice] = useState("");
  return <>
    <Heading title="Usuarios de plataforma" text="Administra accesos y sesiones del equipo de Raíz Digital."
      action={<NewButton onClick={() => setForm("create")}>Crear usuario</NewButton>} />
    <Note>{notice}</Note>
    <div className="commercial-actions export-actions">
      <Button variant="outline" onClick={() => setForm("invite")}>Invitar usuario</Button>
      <Button variant="outline" onClick={() => setRoles(true)}>Configurar permisos</Button>
    </div>
    {query.data ? <Table rows={query.data} rowKey={(row) => row.id} columns={[
      { label: "Nombre", cell: (row) => row.name }, { label: "Correo", cell: (row) => row.email },
      { label: "Rol", cell: (row) => platformRoles[row.role] ?? row.role },
      { label: "Estado", cell: (row) => <Pill value={row.active ? "active" : "suspended"} /> },
      { label: "Acciones", cell: (row) => <div className="commercial-actions">
        <Button variant="ghost" onClick={() => setForm(row)}>Editar</Button>
        <Button variant="ghost" onClick={() => setSessions(row)}>Sesiones</Button></div> },
    ]} /> : <Load error={query.error} retry={query.refetch} />}
    {form && <AccountForm mode={typeof form === "string" ? form : "edit"}
      account={typeof form === "string" ? undefined : form} close={() => setForm(null)}
      done={(status) => { setForm(null); setNotice(status === "simulated" ? "Invitación simulada."
        : status ? "Invitación enviada." : "Usuario guardado."); }} />}
    {sessions && <Sessions account={sessions} close={() => setSessions(null)} />}
    {roles && <Roles close={() => setRoles(false)} />}
  </>;
}

export function Smtp() {
  const query = useData<SMTP>("/platform/smtp");
  const [notice, setNotice] = useState("");
  const change = useChange(() => setNotice("Configuración SMTP guardada."));
  const send = useChange<{ status: string }>((response) => setNotice(response.status === "simulated"
    ? "Prueba simulada. El proveedor de pruebas registró el resultado." : "Correo de prueba enviado."));
  const data = query.data;
  return <>
    <Heading title="Correo SMTP" text="Configura el remitente y verifica la entrega." />
    <Note>{notice}</Note>
    {data ? <div className="commercial-chart-grid">
      <form className="panel commercial-inset" onSubmit={(event) => {
        const fields = entries(event);
        const password = getText(fields, "password");
        change.mutate({ path: "/platform/smtp", method: "PUT", body: {
          ...Object.fromEntries(fields), port: Number(fields.get("port")),
          enabled: fields.has("enabled"), password: password || null,
        } });
      }}>
        <h2>Servidor de correo</h2>
        {data.mode === "mock" && <Pill value="simulated" />}
        <Fields fields={[
          required("host", "Servidor SMTP"), { ...required("port", "Puerto", "number"), min: 1, max: 65535 },
          { name: "username", label: "Usuario SMTP" }, { name: "password", label: "Contraseña SMTP", type: "password",
            hint: data.has_password ? "Deja vacío para conservar la contraseña cifrada." : "Se guarda cifrada." },
          { name: "sender_name", label: "Nombre del remitente" }, required("sender_email", "Correo del remitente", "email"),
          select("security", "Seguridad de conexión", { starttls: "STARTTLS", ssl: "SSL/TLS" }),
          { name: "enabled", label: "Servicio habilitado", type: "checkbox" },
        ]} initial={{ port: 587, security: "starttls", ...data }} />
        {panelError(change.error)}<Save pending={change.isPending}>Guardar SMTP</Save>
      </form>
      <form className="panel commercial-inset align-start" onSubmit={(event) => send.mutate({
        path: "/platform/smtp/test", body: Object.fromEntries(entries(event)),
      })}>
        <h2>Correo de prueba</h2>
        <Fields fields={[required("email", "Correo destinatario", "email")]} />
        {panelError(send.error)}<Save pending={send.isPending || !data.enabled}>Enviar correo de prueba</Save>
      </form>
    </div> : <Load error={query.error} retry={query.refetch} />}
  </>;
}

const assetNames: Record<string, string> = {
  logo: "Logo principal", favicon: "Favicon", "login-logo": "Logo del login", "login-background": "Fondo del login",
};
function AssetEditor({ asset, current }: { asset: string; current: boolean }) {
  const [message, setMessage] = useState("");
  const [localError, setLocalError] = useState("");
  const [revision, setRevision] = useState(0);
  const change = useChange(() => { setMessage("Imagen actualizada."); setRevision((value) => value + 1); });
  const path = `/platform/branding/assets/${asset}`;
  async function upload(event: FormEvent<HTMLFormElement>) {
    const data = entries(event);
    const file = data.get("image");
    if (!(file instanceof File) || !file.size) return;
    setLocalError(""); setMessage("");
    try { change.mutate({ path, method: "PUT", body: { content: await fileContent(file) } }); }
    catch (reason) { setLocalError(errorText(reason)); }
  }
  return <section className="panel commercial-inset commercial-stack">
    <h2>{assetNames[asset]}</h2>
    {current ? <Image unoptimized className="brand-preview" alt={assetNames[asset]} width={320} height={140}
      src={`/api/branding/assets/${asset}?revision=${revision}`} />
      : <p>Imagen predeterminada en uso.</p>}
    <form onSubmit={upload}>
      <Fields fields={[{ ...required("image", `Archivo para ${assetNames[asset]}`, "file"),
        accept: "image/png,image/jpeg,image/webp,image/x-icon", hint: "Hasta 2 MB y 2400 px por lado." }]} />
      <div className="commercial-actions"><Save pending={change.isPending}>Guardar imagen</Save>
        {current && <Button type="button" variant="outline" disabled={change.isPending} onClick={() => {
          if (window.confirm("¿Restaurar la imagen predeterminada?")) change.mutate({ path, method: "DELETE" });
        }}>Restaurar imagen</Button>}</div>
    </form>
    <Note>{message}</Note>{localError && <p className="field-error" role="alert">{localError}</p>}{panelError(change.error)}
  </section>;
}

export function Customize({ login = false }: { login?: boolean }) {
  const query = useData<Branding>("/branding");
  const [notice, setNotice] = useState("");
  const change = useChange(() => setNotice("Personalización guardada."));
  return <>
    <Heading title={login ? "Logo del login" : "Personalización"} text={login
      ? "Configura el logotipo y el fondo de la pantalla de acceso." : "Ajusta la identidad visual y los datos de contacto."} />
    <Note>{notice}</Note>
    {query.data ? <div className="commercial-stack">
      {!login && <form className="panel commercial-inset" onSubmit={(event) => change.mutate({
        path: "/platform/branding", method: "PUT", body: Object.fromEntries(entries(event)),
      })}>
        <Fields initial={{ ...query.data }} fields={[
          required("name", "Nombre de la plataforma"), { name: "support_email", label: "Correo de soporte", type: "email" },
          { name: "contact", label: "Información de contacto" }, { name: "footer", label: "Texto del pie" },
          { name: "primary", label: "Color de marca", type: "color" },
        ]} />
        {panelError(change.error)}<Save pending={change.isPending}>Guardar personalización</Save>
      </form>}
      <div className="commercial-chart-grid">{(login ? ["login-logo", "login-background"] : ["logo", "favicon"]).map(
        (asset) => <AssetEditor key={asset} asset={asset} current={query.data?.assets.includes(asset) ?? false} />)}</div>
      {login && <Button asChild variant="outline"><Link href="/login?preview=1" target="_blank">Previsualizar pantalla de acceso</Link></Button>}
    </div> : <Load error={query.error} retry={query.refetch} />}
  </>;
}

export function Backups({ open, user }: { open: boolean; user: Identity }) {
  const query = useData<{ items: Backup[]; settings: BackupPolicy }>("/platform/backups");
  const [newBackup, setNewBackup] = useState(open);
  const [notice, setNotice] = useState("");
  const create = useChange(() => { setNewBackup(false); setNotice("Respaldo generado y verificado."); });
  const verify = useChange<{ valid: boolean }>((result) => setNotice(result.valid ? "Integridad verificada." : "La verificación de integridad falló."));
  const change = useChange(() => setNotice("Política de respaldos guardada."));
  const canDownload = user.platform_permissions.includes("backups.download");
  return <>
    <Heading title="Respaldos" text="Genera y verifica copias consistentes de SQLite."
      action={<NewButton onClick={() => setNewBackup(true)}>Generar respaldo</NewButton>} />
    <Note>{notice}</Note>{panelError(verify.error)}
    {query.data ? <div className="commercial-stack">
      <Table rows={query.data.items} rowKey={(row) => row.id} columns={[
        { label: "Fecha", cell: (row) => formatDate(row.created_at) },
        { label: "Tamaño (KiB)", cell: (row) => Math.round(row.size / 1024).toLocaleString("es-GT") },
        { label: "Revisión", cell: (row) => row.revision }, { label: "Estado", cell: (row) => <Pill value={row.state} /> },
        { label: "Acciones", cell: (row) => row.state !== "expired" && <div className="commercial-actions">
          <Button variant="ghost" disabled={verify.isPending} onClick={() =>
            verify.mutate({ path: `/platform/backups/${row.id}/verify` })}>Verificar</Button>
          {canDownload && row.state === "verified" && ["db", "manifest"].map((format) =>
            <Button key={format} asChild variant="ghost"><a href={`/api/platform/backups/${row.id}/download/${format}`}>
              {format === "db" ? "Descargar base" : "Manifiesto"}</a></Button>)}</div> },
      ]} />
      <form className="panel commercial-inset" onSubmit={(event) => {
        const fields = entries(event);
        change.mutate({ path: "/platform/backups/settings", method: "PUT", body: {
          automatic: fields.has("automatic"), interval_hours: Number(fields.get("interval_hours")),
          retention_days: Number(fields.get("retention_days")),
        } });
      }}>
        <h2>Programación y retención</h2>
        <Fields initial={{ ...query.data.settings }} fields={[
          { ...required("interval_hours", "Frecuencia (horas)", "number"), min: 1, max: 720 },
          { ...required("retention_days", "Retención (días)", "number"), min: 1, max: 3650 },
          { name: "automatic", label: "Habilitar ejecución programada", type: "checkbox" },
        ]} />
        {panelError(change.error)}<Save pending={change.isPending}>Guardar política</Save>
      </form>
    </div> : <Load error={query.error} retry={query.refetch} />}
    {newBackup && <Modal title="Generar respaldo" close={() => setNewBackup(false)}>
      <div className="commercial-stack"><p>La copia se verificará antes de aparecer disponible.</p>
        {panelError(create.error)}<Button disabled={create.isPending} onClick={() => create.mutate({ path: "/platform/backups" })}>
          {create.isPending ? "Generando…" : "Generar y verificar"}
        </Button>
      </div>
    </Modal>}
  </>;
}

export function Audit() {
  const [filters, setFilters] = useState<Record<string, string>>({});
  const query = useData<AuditItem[]>(`/platform/audit?${queryString(filters)}`);
  return <>
    <Heading title="Auditoría" text="Consulta las operaciones administrativas y su resultado." />
    <form className="panel commercial-inset" onSubmit={(event) => {
      const fields = entries(event);
      const start = getText(fields, "start"), end = getText(fields, "end");
      setFilters({ q: getText(fields, "q"), restaurant: getText(fields, "restaurant"), result: getText(fields, "result"),
        start: start ? String(Date.parse(`${start}T00:00:00-06:00`) / 1000) : "",
        end: end ? String(Date.parse(`${end}T23:59:59-06:00`) / 1000) : "" });
    }}>
      <Fields fields={[{ name: "q", label: "Acción o usuario" }, { name: "restaurant", label: "Código de restaurante" },
        { name: "start", label: "Desde", type: "date" }, { name: "end", label: "Hasta", type: "date" },
        { ...select("result", "Resultado", { ok: "Correcto", failed: "Falló", simulated: "Simulado", sent: "Enviado" }), required: false }]} />
      <Save pending={query.isFetching}>Filtrar</Save>
    </form>
    {query.data ? <Table rows={query.data} rowKey={(row) => row.id} columns={[
      { label: "Fecha y hora", cell: (row) => new Intl.DateTimeFormat("es-GT", { dateStyle: "short", timeStyle: "short", timeZone: "America/Guatemala" }).format(row.created_at * 1000) },
      { label: "Usuario", cell: (row) => row.user }, { label: "Restaurante", cell: (row) => row.restaurant ?? "—" },
      { label: "Acción", cell: (row) => row.action }, { label: "Entidad", cell: (row) => row.subject },
      { label: "Resultado", cell: (row) => label(row.result) }, { label: "Detalles", cell: (row) => row.detail || "—" },
    ]} /> : <Load error={query.error} retry={query.refetch} />}
  </>;
}

export function Notifications() {
  const query = useData<NoticeItem[]>("/platform/notifications");
  const [unread, setUnread] = useState(false);
  const change = useChange();
  return <>
    <Heading title="Notificaciones" text="Revisa avisos de vigencia, cobros y operaciones." />
    <label className="check export-actions"><input type="checkbox" checked={unread} onChange={(event) => setUnread(event.target.checked)} />
      Solo pendientes de leer</label>
    {panelError(change.error)}
    {query.data ? <Table rows={query.data.filter((row) => !unread || !row.read)} rowKey={(row) => row.id} columns={[
      { label: "Fecha", cell: (row) => formatDate(row.created_at) }, { label: "Notificación", cell: (row) => row.message },
      { label: "Lectura", cell: (row) => row.read ? "Leída" : <Button variant="ghost" disabled={change.isPending}
        onClick={() => change.mutate({ path: `/platform/notifications/${row.id}/read` })}>Marcar leída</Button> },
    ]} /> : <Load error={query.error} retry={query.refetch} />}
  </>;
}

function TicketForm({ close, done }: { close: () => void; done: () => void }) {
  const restaurants = useData<{ slug: string; name: string }[]>("/platform/restaurant-options");
  const change = useChange(done);
  return <Modal title="Nueva solicitud" close={close}><form onSubmit={(event) =>
    change.mutate({ path: "/platform/support", body: Object.fromEntries(entries(event)) })}>
    <Fields fields={[
      { ...required("restaurant", "Restaurante", "select"), items: restaurants.data?.map((row) => ({ value: row.slug, label: row.name })) },
      required("subject", "Asunto"), required("description", "Descripción", "textarea"),
      select("priority", "Prioridad", { low: "Baja", normal: "Normal", high: "Alta" }),
    ]} initial={{ priority: "normal" }} />
    {panelError(change.error || restaurants.error)}<Save pending={change.isPending}>Crear solicitud</Save>
  </form></Modal>;
}

function TicketInspect({ ticket, close }: { ticket: Ticket; close: () => void }) {
  const path = `/platform/support/${ticket.id}`;
  const query = useData<TicketDetail>(path);
  const assignees = useData<{ id: string; name: string }[]>("/platform/support-assignees");
  const [notice, setNotice] = useState("");
  const change = useChange(() => setNotice("Solicitud actualizada."));
  return <Modal title={ticket.subject} close={close}>
    <Note>{notice}</Note>
    {query.data ? <div className="commercial-stack">
      <p>{query.data.restaurant_name} · {label(query.data.priority)}</p><p>{query.data.description}</p>
      <form onSubmit={(event) => {
        const data = entries(event);
        change.mutate({ path, method: "PUT", body: {
          state: data.get("state"), assignee_id: data.get("assignee") || null, message: data.get("message"),
        } });
        (event.target as HTMLFormElement).querySelector("textarea")!.value = "";
      }}>
        <Fields initial={{ state: query.data.state, assignee: query.data.assignee_id }} fields={[
          select("state", "Estado", { open: "Abierto", in_progress: "En seguimiento", closed: "Cerrado" }),
          { name: "assignee", label: "Responsable", type: "select",
            items: assignees.data?.map((row) => ({ value: row.id, label: row.name })) },
          { name: "message", label: "Comentario", type: "textarea" },
        ]} />
        {panelError(change.error || assignees.error)}<Save pending={change.isPending}>Guardar seguimiento</Save>
      </form>
      <h2>Historial</h2><Table rows={query.data.history} rowKey={(row) => row.id} columns={[
        { label: "Fecha", cell: (row) => formatDate(row.created_at) }, { label: "Usuario", cell: (row) => row.user },
        { label: "Estado", cell: (row) => label(row.state) }, { label: "Comentario", cell: (row) => row.message || "—" },
      ]} />
    </div> : <Load error={query.error} retry={query.refetch} />}
  </Modal>;
}

export function Support() {
  const [creating, setCreating] = useState(false);
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [filter, setFilter] = useState("");
  const [notice, setNotice] = useState("");
  const query = useData<Ticket[]>(`/platform/support?${queryString({ state: filter })}`);
  return <>
    <Heading title="Soporte" text="Gestiona solicitudes y su seguimiento por restaurante."
      action={<NewButton onClick={() => setCreating(true)}>Nueva solicitud</NewButton>} />
    <Note>{notice}</Note>
    <div className="commercial-filters"><label>Estado<select value={filter} onChange={(event) => setFilter(event.target.value)}>
      <option value="">Todos</option>{["open", "in_progress", "closed"].map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label></div>
    {query.data ? <Table rows={query.data} rowKey={(row) => row.id} columns={[
      { label: "Asunto", cell: (row) => <button className="text-link" onClick={() => setTicket(row)}>{row.subject}</button> },
      { label: "Restaurante", cell: (row) => row.restaurant_name }, { label: "Prioridad", cell: (row) => label(row.priority) },
      { label: "Estado", cell: (row) => <Pill value={row.state} /> }, { label: "Responsable", cell: (row) => row.assignee ?? "Sin asignar" },
    ]} /> : <Load error={query.error} retry={query.refetch} />}
    {creating && <TicketForm close={() => setCreating(false)} done={() => { setCreating(false); setNotice("Solicitud registrada."); }} />}
    {ticket && <TicketInspect ticket={ticket} close={() => setTicket(null)} />}
  </>;
}

export function General() {
  const query = useData<{ payment_methods: string[]; platform_name: string; notification_email?: string }>("/platform/settings");
  const [notice, setNotice] = useState("");
  const change = useChange(() => setNotice("Configuración guardada."));
  return <>
    <Heading title="Configuración general" text="Define los métodos que se ofrecen al registrar cobros." />
    <Note>{notice}</Note>
    {query.data ? <form className="panel commercial-inset" onSubmit={(event) => {
      const data = entries(event);
      change.mutate({ path: "/platform/settings", method: "PUT", body: {
        platform_name: getText(data, "platform_name"), payment_methods: lines(data, "payment_methods"),
        notification_email: getText(data, "notification_email"),
      } });
    }}>
      <Fields fields={[required("platform_name", "Nombre interno"),
        { name: "notification_email", label: "Correo para avisos administrativos", type: "email" },
        required("payment_methods", "Métodos de pago (uno por línea)", "textarea")]}
        initial={{ ...query.data, payment_methods: query.data.payment_methods.join("\n") }} />
      {panelError(change.error)}<Save pending={change.isPending} />
    </form> : <Load error={query.error} retry={query.refetch} />}
  </>;
}

export function Security() {
  const query = useData<{ environment: string; platform_mfa_required: boolean; active_sessions: number;
    encryption_configured: boolean }>("/platform/security");
  return <>
    <Heading title="Seguridad" text="Consulta los controles activos en esta instalación." />
    {query.data ? <section className="panel commercial-inset">
      <dl className="commercial-summary">
        <div><dt>Entorno</dt><dd>{query.data.environment}</dd></div>
        <div><dt>MFA obligatorio</dt><dd>{query.data.platform_mfa_required ? "Sí" : "Solo en producción"}</dd></div>
        <div><dt>Sesiones activas</dt><dd>{query.data.active_sessions}</dd></div>
        <div><dt>Clave de cifrado</dt><dd>{query.data.encryption_configured ? "Configurada" : "Por configurar"}</dd></div>
      </dl>
    </section> : <Load error={query.error} retry={query.refetch} />}
  </>;
}

export function Fel() {
  const query = useData<{ integration: string; restaurants: { slug: string; name: string; active: boolean; plan: string }[] }>("/platform/fel");
  return <>
    <Heading title="FEL general" text="Consulta qué restaurantes tienen acceso a FEL según su contrato." />
    {query.data ? <div className="commercial-stack"><div className="panel commercial-inset"><h2>{query.data.integration}</h2></div>
      <Table rows={query.data.restaurants} rowKey={(row) => row.slug} columns={[
        { label: "Restaurante", cell: (row) => row.name }, { label: "Plan", cell: (row) => row.plan },
        { label: "Estado del restaurante", cell: (row) => <Pill value={row.active ? "active" : "suspended"} /> },
      ]} /></div> : <Load error={query.error} retry={query.refetch} />}
  </>;
}
