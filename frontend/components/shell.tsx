"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  ChevronsUpDown, LogOut, Menu, PanelLeftClose,
  PanelLeftOpen, Store, X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type CSSProperties, type ReactNode } from "react";
import { Brand } from "@/components/brand";
import { ApiError, api, type Identity } from "@/lib/api";
import { platformNavigation } from "@/lib/platform-nav";
import { restaurantNavigation, restaurantRights } from "@/lib/restaurant-nav";
import { apiRoot, Photo } from "@/components/restaurant/shared";
import { useData } from "@/components/platform/shared";

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
  const tenantSlug = user.tenant?.slug ?? "";
  const { data: appearance } = useData<{ display_name: string; accent: string; logo_id: string | null }>(
    `${apiRoot(tenantSlug)}/appearance`, !user.platform_admin && Boolean(tenantSlug) && user.permissions.includes("dashboard.view"),
  );
  const context = user.platform_admin ? "Plataforma" : appearance?.display_name || user.tenant?.name || "Restaurante";
  const groups = user.platform_admin ? platformNavigation.map(({ heading, items }) => ({
    heading, items: items.filter((item) => user.platform_permissions.includes(item.scope)),
  })) : restaurantNavigation.map(({ heading, items }) => ({
    heading, items: items.filter((item) => restaurantRights(user.permissions, ...item.scopes)),
  }));
  const accent = appearance?.accent;
  const luminance = accent ? [1, 3, 5].map((i) => parseInt(accent.slice(i, i + 2), 16) / 255)
    .map((v) => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4)
    .reduce((total, v, i) => total + v * [.2126, .7152, .0722][i], 0) : 0;
  const style = accent ? ({ "--primary": accent, "--primary-ink": luminance > .179 ? "#000" : "#fff" } as CSSProperties) : undefined;
  const active = (section: string) => path === `${base}/${section}` || path.startsWith(`${base}/${section}/`);
  const parentSection = /\/(areas)$/.test(path) ? "tables"
    : /\/(preparation|payment-methods|pos-settings)$/.test(path) ? "settings" : undefined;
  const current = groups.flatMap((group) => [...group.items]).find((item) => active(item.section) || item.section === parentSection)?.label;
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

  return <div style={style} className={`shell ${collapsed ? "collapsed" : ""} ${mobile ? "menu-open" : ""}`}>
    <a className="skip" href="#main">Saltar al contenido</a>
    {mobile && <button className="mobile-overlay" type="button" aria-label="Cerrar menú" onClick={() => setMenuPath(null)} />}
    <aside className="sidebar" id="sidebar" aria-label="Menú principal">
      <div className="sidebar-brand"><Brand /><button className="icon-button menu-close" type="button"
        aria-label="Cerrar menú" onClick={() => setMenuPath(null)}><X size={20} /></button></div>
      <div className="workspace">
        <span className="workspace-icon">{appearance?.logo_id
          ? <Photo slug={tenantSlug} id={appearance.logo_id} alt="" className="workspace-logo" /> : <Store size={19} />}</span>
        <span className="nav-text"><strong>{context}</strong><small>{user.platform_admin ? "Raíz Digital" : "Restaurante"}</small></span>
        {user.restaurants.length > 1 && <Link href="/restaurantes" aria-label="Cambiar restaurante" title="Cambiar restaurante"
          className="icon-button change-workspace"><ChevronsUpDown size={16} /></Link>}
      </div>
      <nav aria-label="Secciones" className="sidebar-sections">
        {groups.filter((group) => group.items.length).map(({ heading, items }) => <div className="nav-group" key={heading}>
          <p className="nav-heading">{heading}</p>
          {items.map((item) => {
            const { label, section, icon: Icon } = item;
            if ("phase" in item && item.phase) return <span key={section} className="nav-link nav-pending"
              title={`${label} · Pendiente para Fase ${item.phase}`}>
              <Icon size={17} /><span className="nav-text">{label}<small>Fase {item.phase} · Pendiente</small></span>
            </span>;
            return <Link key={section} href={`${base}/${section}`}
              aria-label={"accessible" in item ? item.accessible : undefined}
              aria-current={active(section) || section === parentSection ? "page" : undefined} className="nav-link" title={label}
              onClick={() => setMenuPath(null)} prefetch={false}>
              <Icon size={17} /><span className="nav-text">{label}</span>
            </Link>;
          })}
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
