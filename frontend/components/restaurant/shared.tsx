"use client";

import Image from "next/image";
import { useState, type ReactNode, type FormEvent } from "react";
import { Camera, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import {
  Fields, Load, panelError, useData, type FormField,
} from "@/components/platform/shared";

export interface Entry { id: string; name: string; [key: string]: unknown }
export interface PageData<T> { items: T[]; total: number }
export interface MediaFile extends Entry { folder_id: string | null; size: number; width: number; height: number }
export interface Folder extends Entry { parent_id: string | null }
export interface Count { admins: number; staff: number; total: number }
export interface Limits { max_admins: number; max_staff: number; max_total: number }

export const apiRoot = (slug: string) => `/restaurants/${slug}`;
export const resourcePath = (slug: string, resource: string) => `${apiRoot(slug)}/records/${resource}`;
export const value = (entry: Entry, key: string) => String(entry[key] ?? "");
export const required = (name: string, label: string, type?: FormField["type"]): FormField =>
  ({ name, label, type, required: true });
export const numberField = (name: string, label: string, min = 0, step?: string): FormField =>
  ({ name, label, type: "number", required: true, min, step });
export const checkbox = (name: string, label: string): FormField => ({ name, label, type: "checkbox" });
export const options = (name: string, label: string, items: { value: string; label: string }[],
                        required = true): FormField => ({ name, label, type: "select", items, required });
export const choices = (items?: Entry[]) => items?.map((item) => ({ value: item.id, label: item.name })) ?? [];
export const onOff = { true: "Activo", false: "Inactivo" };
export const tableStates: Record<string, string> = {
  available: "Disponible", cleaning: "En limpieza", out_of_service: "Fuera de servicio",
  occupied: "Ocupada", reserved: "Reservada", payment_due: "Pendiente de cobro",
};
export const enumerated = (items: Record<string, string>) =>
  Object.entries(items).map(([value, label]) => ({ value, label }));

export function toCents(amount: string) {
  const trimmed = amount.trim();
  const sign = trimmed.startsWith("-") ? -1 : 1;
  const [integer, decimal = ""] = trimmed.replace(/^[+-]/, "").split(".");
  return sign * (Number(integer || 0) * 100 + Number(decimal.padEnd(2, "0")));
}

export function parseFields(fields: FormField[], data: FormData) {
  const result: Record<string, unknown> = {};
  for (const field of fields) {
    const raw = String(data.get(field.name) ?? "");
    result[field.name] = field.type === "checkbox" ? data.has(field.name)
      : field.name === "price_cents" ? toCents(raw)
        : field.type === "number" ? Number(raw)
          : field.type === "select" && field.name.endsWith("_id") ? raw || null : raw;
  }
  return result;
}

export function mediaUrl(slug: string, id: string, thumb = true) {
  return `/api${apiRoot(slug)}/media/files/${id}/content${thumb ? "?thumb=true" : ""}`;
}

export function Photo({ slug, id, alt, className = "" }: {
  slug: string; id?: string | null; alt: string; className?: string;
}) {
  return id
    ? <Image className={`restaurant-photo ${className}`} unoptimized src={mediaUrl(slug, id)}
        alt={alt} width={320} height={200} referrerPolicy="no-referrer" />
    : <div className={`restaurant-photo restaurant-placeholder ${className}`} aria-hidden><Camera size={28} /></div>;
}

export async function uploadPhoto(slug: string, file: File, folder: string | null, max: number) {
  if (!file.size || file.size > max) throw new Error("La imagen excede el tamaño permitido o está vacía.");
  const encoded = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
    reader.onerror = () => reject(new Error("No se pudo leer la imagen."));
    reader.readAsDataURL(file);
  });
  return api<MediaFile>(`${apiRoot(slug)}/media/files`, {
    method: "POST", body: JSON.stringify({ name: file.name.slice(0, 100), folder_id: folder, content: encoded }),
  });
}

export function Pager({ page, total, size = 20, setPage }: {
  page: number; total: number; size?: number; setPage: (page: number) => void;
}) {
  if (page === 1 && total <= size) return null;
  return <div className="pagination">
    <span>Página {page} de {Math.max(1, Math.ceil(total / size))}</span>
    <Button type="button" variant="outline" disabled={page <= 1} aria-label="Página anterior"
      onClick={() => setPage(page - 1)}><ChevronLeft size={17} /></Button>
    <Button type="button" variant="outline" disabled={page * size >= total} aria-label="Página siguiente"
      onClick={() => setPage(page + 1)}><ChevronRight size={17} /></Button>
  </div>;
}

export function PhotoPicker({ slug, title, selected, change, allowed }: {
  slug: string; title: string; selected: string; change: (id: string) => void; allowed: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [issue, setIssue] = useState<Error | null>(null);
  const [uploading, setUploading] = useState(false);
  const results = useData<PageData<MediaFile>>(`${resourcePath(slug, "files")}?q=${encodeURIComponent(query)}&page=${page}&size=8`, open);
  const limit = useData<{ max_bytes: number }>(`${apiRoot(slug)}/media/limits`, allowed && open);
  return <section className="panel commercial-inset commercial-stack photo-picker">
    <div className="commercial-row"><h2>{title}</h2>{allowed && <Button type="button" variant="outline"
      onClick={() => setOpen(!open)}>{open ? "Cerrar biblioteca" : "Elegir imagen"}</Button>}</div>
    {selected && <div className="commercial-actions"><Photo slug={slug} id={selected} alt={title} className="restaurant-thumbnail" />
      <Button type="button" variant="ghost" onClick={() => change("")}>Quitar imagen</Button></div>}
    {open && <>
      <label className="field">Buscar fotografías<input type="search" value={query}
        onChange={(event) => { setQuery(event.target.value); setPage(1); }} /></label>
      <label className="field">Subir imagen
        <input type="file" accept="image/jpeg,image/png,image/webp,image/avif" disabled={uploading}
          onChange={async (event) => {
            const file = event.target.files?.[0]; if (!file) return;
            setIssue(null); setUploading(true);
            try {
              const image = await uploadPhoto(slug, file, null, limit.data?.max_bytes ?? 8_388_608);
              change(image.id); setOpen(false); void results.refetch();
            } catch (error) { setIssue(error instanceof Error ? error : new Error("No se pudo subir.")); }
            finally { setUploading(false); }
          }} /></label>
      {panelError(issue)}
      {results.data ? <>
        <div className="picker-grid">{results.data.items.map((image) =>
          <button type="button" key={image.id} onClick={() => { change(image.id); setOpen(false); }}
            className="panel picker-option" aria-label={`Elegir ${image.name}`}>
            <Photo slug={slug} id={image.id} alt="" /><span>{image.name}</span>
          </button>)}</div>
        {!results.data.items.length && <p>La biblioteca todavía no tiene resultados.</p>}
        <Pager page={page} size={8} total={results.data.total} setPage={setPage} />
      </> : <Load error={results.error} retry={results.refetch} />}
    </>}
  </section>;
}

export function Seats({ used, limits, assigned }: { used: Count; limits: Limits; assigned?: Count }) {
  const all = [
    ["Administradores", used.admins, limits.max_admins, assigned?.admins],
    ["Operativos", used.staff, limits.max_staff, assigned?.staff],
    ["Total", used.total, limits.max_total, assigned?.total],
  ] as const;
  return <div className="seats-grid">{all.map(([title, used, max, committed]) => <div key={title}>
    <p>{title} · {used}/{max}{committed !== undefined && committed > used ? ` · ${committed - used} en invitaciones` : ""}</p>
    <progress value={committed ?? used} max={max || 1} aria-label={title} />
  </div>)}</div>;
}

export function Segments({ values, selected, change, label }: {
  values: string[]; selected: string; change: (value: string) => void; label: string;
}) {
  return <nav className="commercial-tabs" aria-label={label}>{values.map((name) =>
    <Button key={name} type="button" variant={selected === name ? "outline" : "ghost"}
      aria-pressed={selected === name} onClick={() => change(name)}>{name}</Button>)}</nav>;
}

export function FieldSection({ title, fields, initial, children }: {
  title: string; fields: FormField[]; initial: Record<string, unknown>; children?: ReactNode;
}) {
  return <fieldset className="restaurant-fieldset">
    <legend>{title}</legend><Fields fields={fields} initial={initial} />{children}
  </fieldset>;
}

export function formData(event: FormEvent<HTMLFormElement>) {
  event.preventDefault();
  return new FormData(event.currentTarget);
}
