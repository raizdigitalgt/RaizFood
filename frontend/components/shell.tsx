"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  ChevronsUpDown, LayoutDashboard, LogOut, Menu, PanelLeftClose,
  PanelLeftOpen, Store, UsersRound, X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { Brand } from "@/components/brand";
import { ApiError, api, type Identity } from "@/lib/api";
import { platformNavigation } from "@/lib/platform-nav";

export function Shell({ user, children }: { user: Identity; children: ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const cache = useQueryClient();
  const [collapsed, setCollapsed] = useState(false);
  const [menuPath, setMenuPath] = useState<string | null>(null);
  const mobile = menuPath === path;
  const [logoutError, setLogoutError] = useState("");
  const [pending, setPending] = useState(false);
  const base = user.platform_admin ? "/platform" : `/app/${user.tenant?.slug}`;
  const context = user.platform_admin ? "Plataforma" : user.tenant?.name ?? "Restaurante";
  const groups = user.platform_admin ? platformNavigation.map(({ heading, items }) => ({
    heading, items: items.filter((item) => user.platform_permissions.includes(item.scope)),
  })) : [{ heading: "Restaurante", items: [
    { label: "Resumen", section: "dashboard", icon: LayoutDashboard },
    ...(user.permissions.includes("users.manage") ? [{ label: "Equipo", section: "team", icon: UsersRound }] : []),
  ] }];
  const active = (section: string) => path === `${base}/${section}` || path.startsWith(`${base}/${section}/`);
  const current = groups.flatMap((group) => group.items).find((item) => active(item.section))?.label;
  const initials = user.name.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();

  async function logout() {
    setPending(true);
    setLogoutError("");
    try {
      await api("/auth/logout", { method: "POST" }, false);
      cache.clear();
      router.replace("/login");
      router.refresh();
    } catch (reason) {
      setLogoutError(reason instanceof ApiError ? reason.message : "No se pudo cerrar la sesión.");
      setPending(false);
    }
  }

  return <div className={`shell ${collapsed ? "collapsed" : ""} ${mobile ? "menu-open" : ""}`}>
    <a className="skip" href="#main">Saltar al contenido</a>
    {mobile && <button className="mobile-overlay" type="button" aria-label="Cerrar menú" onClick={() => setMenuPath(null)} />}
    <aside className="sidebar" id="sidebar" aria-label="Menú principal">
      <div className="sidebar-brand"><Brand /><button className="icon-button menu-close" type="button"
        aria-label="Cerrar menú" onClick={() => setMenuPath(null)}><X size={20} /></button></div>
      <div className="workspace">
        <span className="workspace-icon"><Store size={19} /></span>
        <span className="nav-text"><strong>{context}</strong><small>{user.platform_admin ? "Raíz Digital" : "Restaurante"}</small></span>
        {user.restaurants.length > 1 && <Link href="/restaurantes" aria-label="Cambiar restaurante" title="Cambiar restaurante"
          className="icon-button change-workspace"><ChevronsUpDown size={16} /></Link>}
      </div>
      <nav aria-label="Secciones" className="sidebar-sections">
        {groups.filter((group) => group.items.length).map(({ heading, items }) => <div className="nav-group" key={heading}>
          <p className="nav-heading">{heading}</p>
          {items.map(({ label, section, icon: Icon }) => <Link key={section} href={`${base}/${section}`}
            aria-current={active(section) ? "page" : undefined} className="nav-link" title={label}
            onClick={() => setMenuPath(null)} prefetch={false}>
            <Icon size={17} /><span className="nav-text">{label}</span>
          </Link>)}
        </div>)}
      </nav>
      <div className="sidebar-footer">
        <button type="button" className="nav-link collapse-button" aria-label={collapsed ? "Expandir menú" : "Colapsar menú"}
          onClick={() => setCollapsed(!collapsed)}>
          {collapsed ? <PanelLeftOpen size={19} /> : <PanelLeftClose size={19} />}<span className="nav-text">Colapsar menú</span>
        </button>
      </div>
    </aside>
    <div className="content-frame">
      <header className="topbar">
        <button className="icon-button mobile-trigger" type="button" aria-label="Abrir menú" aria-expanded={mobile}
          aria-controls="sidebar" onClick={() => setMenuPath(path)}><Menu size={23} /></button>
        <nav className="breadcrumb" aria-label="Ruta actual"><span>{context}</span><span aria-hidden>/</span>
          <strong>{current}</strong></nav>
        <details className="profile">
          <summary><span className="avatar">{initials}</span><span className="profile-name">{user.name}</span></summary>
          <div className="profile-menu panel"><strong>{user.name}</strong><small>{user.email}</small>
            {logoutError && <p role="alert" className="field-error">{logoutError}</p>}
            <button className="nav-link" type="button" disabled={pending} onClick={logout}><LogOut size={17} /> Cerrar sesión</button>
          </div>
        </details>
      </header>
      <main id="main" className="main-content">{children}</main>
    </div>
  </div>;
}
