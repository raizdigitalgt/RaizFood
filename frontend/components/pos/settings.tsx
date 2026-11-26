"use client";

import Link from "next/link";
import { useState } from "react";
import { Message } from "@/components/auth";
import { Heading, Load, Note, useChange } from "@/components/platform/shared";
import { apiRoot, resourcePath, toCents } from "@/components/restaurant/shared";
import { Button } from "@/components/ui/button";
import { errorText } from "@/components/platform/shared";
import { FieldRow, usePosData, type PosOptions } from "./shared";

type Config = { kitchen_warning_minutes: number; max_discount_bps: number; max_discount_cents: number };
export function PosSettings({ slug }: { slug: string }) {
  const root = apiRoot(slug);
  const config = usePosData<Config>(`${root}/pos/config`);
  const staff = usePosData<PosOptions>(`${root}/pos/options?customer=`);
  const [member, setMember] = useState("");
  const [notice, setNotice] = useState("");
  const save = useChange(() => {
    setNotice("Política de operación guardada.");
    void config.refetch();
  });
  return <>
    <Heading title="Configuración del POS" text="Ajusta los descuentos y las estaciones de preparación."
      action={<Button asChild variant="outline"><Link href={`/app/${slug}/settings`}>Configuración general</Link></Button>} />
    {config.data ? <form className="panel pos-settings pos-form" onSubmit={(event) => {
      event.preventDefault();
      const values = new FormData(event.currentTarget);
      setNotice("");
      save.mutate({ path: `${root}/pos/config`, method: "PUT", body: {
        kitchen_warning_minutes: Number(values.get("minutes")),
        max_discount_bps: toCents(String(values.get("percent"))),
        max_discount_cents: toCents(String(values.get("amount"))),
      } });
    }}>
      <h2>Política de operación</h2>
      <FieldRow label="Avisar de demora en cocina después de (minutos)"><input name="minutes" type="number" required
        min={1} max={180} defaultValue={config.data.kitchen_warning_minutes} /></FieldRow>
      <div className="pos-form-grid">
        <FieldRow label="Descuento máximo (%)"><input name="percent" type="number" required min={0} max={100}
          step="0.01" defaultValue={config.data.max_discount_bps / 100} /></FieldRow>
        <FieldRow label="Descuento máximo (Q)"><input name="amount" type="number" required min={0} max={1000000}
          step="0.01" defaultValue={config.data.max_discount_cents / 100} /></FieldRow>
      </div>
      {save.error && <Message>{errorText(save.error)}</Message>}
      <Note>{notice}</Note><Button type="submit" disabled={save.isPending}>Guardar política</Button>
    </form> : <Load error={config.error} retry={config.refetch} />}
    <section className="panel pos-settings pos-form">
      <h2>Estaciones por integrante</h2>
      {staff.data ? <FieldRow label="Integrante de cocina"><select value={member} onChange={(event) => setMember(event.target.value)}>
        <option value="">Seleccionar integrante</option>
        {staff.data.station_staff?.map((entry) => <option key={entry.id} value={entry.id}>{entry.name}</option>)}
      </select></FieldRow> : <Load error={staff.error} retry={staff.refetch} />}
      {member && <Stations key={member} slug={slug} member={member} />}
    </section>
  </>;
}
function Stations({ slug, member }: { slug: string; member: string }) {
  const root = apiRoot(slug);
  const path = `${root}/pos/stations/${member}`;
  const assigned = usePosData<{ preparation_ids: string[] }>(path);
  const areas = usePosData<{ items: { id: string; name: string }[] }>(
    `${resourcePath(slug, "preparation")}?active=true&size=100`);
  const [notice, setNotice] = useState("");
  const save = useChange(() => {
    setNotice("Estaciones guardadas.");
    void assigned.refetch();
  });
  if (!assigned.data || !areas.data) return <Load error={assigned.error ?? areas.error}
    retry={() => { void assigned.refetch(); void areas.refetch(); }} />;
  const selected = assigned.data.preparation_ids;
  return <form className="pos-form" onSubmit={(event) => {
    event.preventDefault();
    setNotice("");
    save.mutate({ path, method: "PUT", body: { preparation_ids: new FormData(event.currentTarget).getAll("area") } });
  }}>
    <fieldset className="restaurant-fieldset"><legend>Estaciones permitidas</legend>
      {areas.data.items.length ? areas.data.items.map((entry) => <label key={entry.id} className="check">
        <input type="checkbox" name="area" value={entry.id} defaultChecked={selected.includes(entry.id)} />{entry.name}
      </label>) : <p>Crea áreas de preparación en la configuración del restaurante.</p>}
    </fieldset>
    {save.error && <Message>{errorText(save.error)}</Message>}
    <Note>{notice}</Note><Button type="submit" disabled={save.isPending}>Guardar estaciones</Button>
  </form>;
}
