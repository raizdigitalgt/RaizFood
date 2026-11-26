"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LoaderCircle, Plus, X } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Field, Message } from "@/components/auth";
import { Button } from "@/components/ui/button";
import { ApiError, api, date } from "@/lib/api";

export const states: Record<string, string> = {
  active: "Activa", trial: "En prueba", pending: "Pendiente", grace: "Período de gracia",
  expired: "Vencida", suspended: "Suspendida", cancelled: "Cancelada", confirmed: "Confirmado",
  rejected: "Rechazado", reversed: "Revertido", verified: "Verificado", invalid: "Inválido",
  open: "Abierto", in_progress: "En seguimiento", closed: "Cerrado", low: "Baja",
  normal: "Normal", high: "Alta", initial: "Inicial", renewal: "Renovación",
  monthly: "Mensual", annual: "Anual", simulated: "Simulado", sent: "Enviado", failed: "Falló",
};
export const label = (value: string) => states[value] ?? value;
export const day = (value: string) => {
  const [year, month, number] = value.split("-");
  return number && month ? `${number}/${month}/${year}` : value;
};
export const utcDate = () => new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/Guatemala", year: "numeric", month: "2-digit", day: "2-digit",
}).format(new Date());
export const formatDate = date;
export const errorText = (error: unknown) => error instanceof ApiError
  ? error.message : error instanceof Error ? error.message : "No se pudo completar la solicitud.";

export function useData<T>(path: string, enabled = true) {
  return useQuery({ queryKey: ["commercial", path], queryFn: () => api<T>(path), enabled });
}

export function useChange<T = unknown>(onSuccess?: (data: T) => void) {
  const cache = useQueryClient();
  return useMutation<T, Error, { path: string; method?: string; body?: unknown }>({
    mutationFn: ({ path, method = "POST", body }) => api<T>(path, {
      method, body: body === undefined ? undefined : JSON.stringify(body),
    }),
    onSuccess: (data) => {
      void cache.invalidateQueries({ queryKey: ["commercial"] });
      void cache.invalidateQueries({ queryKey: ["platform-dashboard"] });
      void cache.invalidateQueries({ queryKey: ["restaurants"] });
      void cache.invalidateQueries({ queryKey: ["plans"] });
      onSuccess?.(data);
    },
  });
}

export function Heading({ title, text, action }: { title: string; text: string; action?: ReactNode }) {
  return <div className="page-heading"><div><h1>{title}</h1><p>{text}</p></div>{action}</div>;
}

export function NewButton({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return <Button onClick={onClick}><Plus size={18} />{children}</Button>;
}

export function Load({ error, retry }: { error: Error | null; retry?: () => void }) {
  if (!error) return <div role="status" aria-label="Cargando información" className="panel skeleton" />;
  return <div className="panel empty"><Message>{errorText(error)}</Message>
    {retry && <Button variant="outline" onClick={retry}>Reintentar</Button>}</div>;
}

export function Note({ children }: { children: ReactNode }) {
  return children && <p className="success-message" role="status">{children}</p>;
}

export function Table<T>({ rows, columns, rowKey }: {
  rows: T[]; columns: { label: string; cell: (item: T) => ReactNode }[];
  rowKey: (item: T) => string;
}) {
  if (!rows.length) return <div className="panel empty"><p>No hay registros para mostrar.</p></div>;
  return <section className="panel table-scroll"><table>
    <thead><tr>{columns.map((column) => <th key={column.label} scope="col">{column.label}</th>)}</tr></thead>
    <tbody>{rows.map((row) => <tr key={rowKey(row)}>{columns.map((column) =>
      <td key={column.label}>{column.cell(row)}</td>)}</tr>)}</tbody>
  </table></section>;
}

export function Pill({ value }: { value: string }) {
  return <span className={`status ${["active", "confirmed", "verified"].includes(value) ? "status-active" : ""}`}>
    <i />{label(value)}</span>;
}

export function Modal({ title, close, children }: { title: string; close: () => void; children: ReactNode }) {
  return <dialog className="modal panel commercial-modal" ref={(node) => { if (node && !node.open) node.showModal(); }}
    aria-label={title} onCancel={close} onClose={close}>
    <div className="modal-header"><h2>{title}</h2>
      <button className="icon-button" type="button" onClick={close} aria-label="Cerrar"><X size={20} /></button>
    </div>{children}
  </dialog>;
}

export interface FormField {
  name: string;
  label: string;
  type?: "text" | "email" | "password" | "number" | "date" | "textarea" | "checkbox" | "color" | "file" | "select";
  required?: boolean;
  min?: number;
  max?: number;
  step?: string;
  items?: { value: string; label: string }[];
  accept?: string;
  hint?: string;
}

function SelectField({ field, initial }: { field: FormField; initial: string }) {
  const [value, setValue] = useState(initial);
  return <select name={field.name} required={field.required} value={value}
    onChange={(event) => setValue(event.target.value)}>
    <option value="">Seleccionar</option>{field.items?.map((item) =>
      <option key={item.value} value={item.value}>{item.label}</option>)}
  </select>;
}

export function Fields({ fields, initial = {} }: {
  fields: FormField[]; initial?: Record<string, unknown>;
}) {
  return <div className="commercial-fields">{fields.map((field) => {
    const value = String(initial[field.name] ?? "");
    if (field.type === "checkbox") return <label className="check" key={field.name}>
      <input name={field.name} type="checkbox" defaultChecked={Boolean(initial[field.name])} />{field.label}</label>;
    return <div key={field.name}><Field label={field.label}>
      {field.type === "select" ? <SelectField field={field} initial={value} />
        : field.type === "textarea" ? <textarea name={field.name} defaultValue={value} required={field.required} rows={3} />
        : field.type === "file" ? <input name={field.name} type="file" accept={field.accept} required={field.required} />
        : <input name={field.name} type={field.type ?? "text"} defaultValue={value}
            required={field.required} min={field.min} max={field.max} step={field.step}
            autoComplete={field.type === "password" ? "new-password" : undefined} />}
    </Field>{field.hint && <small className="commercial-hint">{field.hint}</small>}</div>;
  })}</div>;
}

export function Save({ pending, children = "Guardar cambios" }: { pending: boolean; children?: ReactNode }) {
  return <Button type="submit" disabled={pending}>{pending && <LoaderCircle className="spin" size={17} />}{children}</Button>;
}

export function entries(event: FormEvent<HTMLFormElement>) {
  event.preventDefault();
  return new FormData(event.currentTarget);
}

export const getText = (data: FormData, name: string) => String(data.get(name) ?? "");
export const lines = (data: FormData, name: string) => getText(data, name).split("\n").map((part) => part.trim()).filter(Boolean);

export function cents(value: string) {
  const [whole, decimal = ""] = value.split(".");
  return Number(whole || 0) * 100 + Number(decimal.padEnd(2, "0"));
}

export function fileContent(file: File) {
  if (file.size > 2 * 1024 * 1024) return Promise.reject(new Error("La imagen supera 2 MB."));
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
    reader.onerror = () => reject(new Error("No se pudo leer el archivo."));
    reader.readAsDataURL(file);
  });
}

export function panelError(error: Error | null) {
  return error && <Message>{errorText(error)}</Message>;
}

export function queryString(values: Record<string, string>) {
  return new URLSearchParams(Object.entries(values).filter(([, value]) => value)).toString();
}
