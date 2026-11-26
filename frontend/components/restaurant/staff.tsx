"use client";

import { UserPlus } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { MemberForm } from "@/components/dashboard";
import { restaurantRights } from "@/lib/restaurant-nav";
import {
  Fields, formatDate, Heading, Load, Modal, NewButton, Note, panelError, Pill,
  Save, Table, useChange, useData,
} from "@/components/platform/shared";
import { apiRoot, checkbox, formData, options, required, Seats, Segments, type Count, type Limits } from "./shared";

interface Staff { id: string; email: string; name: string; role: string; role_code: string; active: boolean; last_access: number | null }
interface Role { code: string; name: string; permissions: string[]; editable: boolean; assignable: boolean }
interface Invitation { email: string; name: string; role: string; state: string; expires_at: number }
interface Session { id: string; expires_at: number; revoked: boolean }

const modules: Record<string, string> = {
  dashboard: "Dashboard", menu: "Menú y extras", categories: "Categorías", tables: "Mesas",
  customers: "Clientes", users: "Usuarios", roles: "Roles", settings: "Configuración",
  media: "Multimedia", subscription: "Suscripción", audit: "Auditoría",
  pos: "Punto de venta · Fase 4", orders: "Pedidos · Fase 4", kitchen: "Comandas · Fase 4",
  inventory: "Inventario · Fase 6", cash: "Caja · Fase 7", fel: "FEL · Fase 7",
};
const actions: Record<string, string> = {
  manage: "Gestionar", view: "Ver", create: "Crear", edit: "Editar", archive: "Archivar",
  export: "Exportar", invite: "Invitar", sessions: "Gestionar sesiones", recover: "Recuperación de cuentas",
  access: "Acceder", issue: "Emitir", update: "Actualizar", checkout: "Cobrar", cancel: "Cancelar",
};

function EditMember({ slug, staff, roles, close, done }: { slug: string; staff: Staff; roles: Role[]; close: () => void; done: () => void }) {
  const change = useChange(done);
  return <Modal title="Editar integrante" close={close}>
    <p>{staff.email}</p>
    <form onSubmit={(event) => {
      const fields = formData(event);
      change.mutate({ path: `${apiRoot(slug)}/staff/${staff.id}`, method: "PUT",
        body: { ...Object.fromEntries(fields), active: fields.has("active") } });
    }}>
      <Fields fields={[required("display_name", "Nombre en este restaurante"),
        options("role_code", "Rol", roles.filter((item) => item.assignable).map((item) => ({ value: item.code, label: item.name }))),
        checkbox("active", "Membresía activa")]} initial={{ display_name: staff.name, role_code: staff.role_code, active: staff.active }} />
      {panelError(change.error)}<Save pending={change.isPending} />
    </form>
  </Modal>;
}

function StaffSessions({ slug, staff, close }: { slug: string; staff: Staff; close: () => void }) {
  const path = `${apiRoot(slug)}/staff/${staff.id}/sessions`;
  const query = useData<Session[]>(path);
  const change = useChange();
  return <Modal title={`Sesiones de ${staff.name}`} close={close}>
    {panelError(change.error)}
    {query.data ? <Table rows={query.data} rowKey={(row) => row.id} columns={[
      { label: "Vencimiento", cell: (row) => formatDate(row.expires_at) },
      { label: "Estado", cell: (row) => row.revoked ? "Revocada" : "Autorizada" },
      { label: "Acción", cell: (row) => !row.revoked && <Button variant="ghost" disabled={change.isPending} onClick={() => {
        if (window.confirm("¿Revocar esta sesión del restaurante?")) change.mutate({ path: `${path}/${row.id}/revoke` });
      }}>Revocar</Button> },
    ]} /> : <Load error={query.error} retry={query.refetch} />}
  </Modal>;
}

function Invite({ slug, roles, previous, close, done }: {
  slug: string; roles: Role[]; previous?: Invitation; close: () => void; done: (state: string) => void;
}) {
  const change = useChange<{ status: string }>((result) => done(result.status));
  return <Modal title={previous ? "Reenviar invitación" : "Invitar usuario"} close={close}>
    <form onSubmit={(event) => change.mutate({ path: `${apiRoot(slug)}/staff-invitations`,
      body: Object.fromEntries(formData(event)) })}>
      <Fields fields={[required("name", "Nombre"), required("email", "Correo electrónico", "email"),
        options("role", "Rol", roles.filter((item) => item.assignable).map((item) => ({ value: item.code, label: item.name })))]}
        initial={previous ? { ...previous } : {}} />
      <p>Las invitaciones vigentes reservan un cupo durante 24 horas.</p>
      {panelError(change.error)}<Save pending={change.isPending}>Enviar invitación</Save>
    </form>
  </Modal>;
}

function RoleForm({ slug, role, available, close, done }: {
  slug: string; role?: Role; available: string[]; close: () => void; done: () => void;
}) {
  const change = useChange(done);
  const groups = [...new Set(available.map((scope) => scope.split(".")[0]))].sort();
  return <Modal title={role ? "Editar rol" : "Crear rol personalizado"} close={close}>
    <form onSubmit={(event) => {
      const fields = formData(event);
      change.mutate({ path: `${apiRoot(slug)}/roles${role ? `/${role.code}` : ""}`, method: role ? "PUT" : "POST",
        body: { name: fields.get("name"), permissions: fields.getAll("permission") } });
    }}>
      <Fields fields={[required("name", "Nombre del rol")]} initial={role ? { name: role.name } : {}} />
      <div className="permissions-matrix">
        {groups.map((group) => <fieldset className="restaurant-fieldset" key={group}>
          <legend>{modules[group] ?? group}</legend><div className="commercial-fields">
            {available.filter((scope) => scope.startsWith(`${group}.`)).map((scope) => {
              const action = scope.split(".")[1];
              return <label className="check" key={scope}><input type="checkbox" name="permission" value={scope}
                defaultChecked={role?.permissions.includes(scope)} />{actions[action] ?? action}</label>;
            })}
          </div>
        </fieldset>)}
      </div>
      {panelError(change.error)}<Save pending={change.isPending}>{role ? "Guardar rol" : "Crear rol"}</Save>
    </form>
  </Modal>;
}

export function StaffView({ slug, permissions, inviteFirst }: { slug: string; permissions: string[]; inviteFirst: boolean }) {
  const pref = apiRoot(slug);
  const canStaff = permissions.includes("users.manage");
  const canInvite = restaurantRights(permissions, "users.manage", "users.invite");
  const canRoles = permissions.includes("roles.manage");
  const tabs = [...(canStaff ? ["Usuarios"] : []), ...(canInvite ? ["Invitaciones"] : []), "Roles"];
  const [tab, setTab] = useState(tabs[0]);
  const [creating, setCreating] = useState(false);
  const [invite, setInvite] = useState<true | Invitation | null>(inviteFirst && canInvite ? true : null);
  const [editing, setEditing] = useState<Staff | null>(null);
  const [sessions, setSessions] = useState<Staff | null>(null);
  const [role, setRole] = useState<true | Role | null>(null);
  const [notice, setNotice] = useState("");
  const cache = useQueryClient();
  const members = useData<{ items: Staff[]; usage: Count; held: Count; limits: Limits }>(`${pref}/staff`, canStaff);
  const roles = useData<{ items: Role[]; permissions: string[] }>(`${pref}/roles`);
  const invites = useData<Invitation[]>(`${pref}/staff-invitations`, canInvite && tab === "Invitaciones");
  const change = useChange(() => setNotice("Solicitud procesada."));
  const status: Record<string, string> = { pending: "Pendiente", expired: "Vencida", cancelled: "Cancelada", accepted: "Aceptada" };
  const assignable = (person: Staff) => roles.data?.items.some((row) => row.code === person.role_code && row.assignable);
  return <>
    <Heading title="Equipo" text="Administra usuarios, invitaciones y roles de este restaurante."
      action={<div className="commercial-actions">
        {canStaff && <NewButton onClick={() => setCreating(true)}>Agregar usuario</NewButton>}
        {canInvite && <Button variant="outline" onClick={() => setInvite(true)}><UserPlus size={18} /> Invitar usuario</Button>}
      </div>} />
    <Note>{notice}</Note>{panelError(change.error)}
    {members.data && <section className="panel commercial-inset export-actions">
      <h2>Cupos del plan</h2><Seats used={members.data.usage} assigned={members.data.held} limits={members.data.limits} />
    </section>}
    <Segments values={tabs} selected={tab} change={setTab} label="Administración del equipo" />
    {tab === "Usuarios" && (members.data ? <Table rows={members.data.items} rowKey={(item) => item.id} columns={[
      { label: "Nombre", cell: (item) => item.name }, { label: "Correo", cell: (item) => item.email },
      { label: "Rol", cell: (item) => item.role }, { label: "Estado", cell: (item) => <Pill value={item.active ? "active" : "Inactivo"} /> },
      { label: "Último acceso", cell: (item) => item.last_access ? formatDate(item.last_access) : "—" },
      { label: "Acciones", cell: (item) => assignable(item) && <div className="commercial-actions">
        <Button variant="ghost" onClick={() => setEditing(item)}>Editar</Button>
        <Button variant="ghost" onClick={() => setSessions(item)}>Sesiones</Button>
        <Button variant="ghost" disabled={change.isPending} onClick={() => {
          if (window.confirm("¿Solicitar un correo de recuperación a esta cuenta?"))
            change.mutate({ path: `${pref}/staff/${item.id}/recover` });
        }}>Recuperación</Button>
      </div> },
    ]} /> : <Load error={members.error} retry={members.refetch} />)}
    {tab === "Roles" && <div className="commercial-stack">
      {canRoles && <NewButton onClick={() => setRole(true)}>Crear rol personalizado</NewButton>}
      {roles.data ? <Table rows={roles.data.items} rowKey={(item) => item.code} columns={[
        { label: "Rol", cell: (item) => item.name },
        { label: "Permisos", cell: (item) => <span className="role-permissions">{item.permissions.join(" · ") || "Sin permisos"}</span> },
        { label: "Acciones", cell: (item) => item.editable && canRoles &&
          <Button variant="ghost" onClick={() => setRole(item)}>Editar rol</Button> },
      ]} /> : <Load error={roles.error} retry={roles.refetch} />}
    </div>}
    {tab === "Invitaciones" && (invites.data ? <Table rows={invites.data} rowKey={(item) => `${item.email}-${item.expires_at}-${item.state}`} columns={[
      { label: "Correo", cell: (item) => item.email },
      { label: "Estado", cell: (item) => <Pill value={status[item.state]} /> },
      { label: "Vencimiento", cell: (item) => formatDate(item.expires_at) },
      { label: "Acciones", cell: (item) => item.state !== "accepted" && <div className="commercial-actions">
        <Button variant="ghost" onClick={() => setInvite(item)}>Reenviar</Button>
        {item.state === "pending" && <Button variant="ghost" disabled={change.isPending} onClick={() => {
          if (window.confirm("¿Cancelar esta invitación?"))
            change.mutate({ path: `${pref}/staff-invitations/cancel`, body: { email: item.email } });
        }}>Cancelar invitación</Button>}
      </div> },
    ]} /> : <Load error={invites.error} retry={invites.refetch} />)}
    {creating && <MemberForm endpoint={`${pref}/members`} choices={roles.data?.items.filter((item) => item.assignable) ?? []}
      close={() => setCreating(false)} done={(name) => {
        setCreating(false); setNotice(`${name} se agregó al equipo.`);
        void cache.invalidateQueries({ queryKey: ["commercial"] });
      }} />}
    {invite && <Invite slug={slug} roles={roles.data?.items ?? []} previous={invite === true ? undefined : invite}
      close={() => setInvite(null)} done={(state) => { setInvite(null); setTab("Invitaciones");
        setNotice(state === "simulated" ? "Invitación simulada." : "Invitación enviada."); }} />}
    {editing && <EditMember slug={slug} staff={editing} roles={roles.data?.items ?? []} close={() => setEditing(null)}
      done={() => { setEditing(null); setNotice("Integrante actualizado."); }} />}
    {sessions && <StaffSessions slug={slug} staff={sessions} close={() => setSessions(null)} />}
    {role && roles.data && <RoleForm slug={slug} role={role === true ? undefined : role} available={roles.data.permissions}
      close={() => setRole(null)} done={() => { setRole(null); setNotice("Rol guardado."); }} />}
  </>;
}
