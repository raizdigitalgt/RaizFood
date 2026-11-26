"use client";

import { Armchair, Grid2X2, List, SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { useDeferredValue, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { money } from "@/lib/api";
import { restaurantRights } from "@/lib/restaurant-nav";
import {
  day, Fields, Heading, Load, Modal, NewButton, Note, panelError, Pill, queryString, Save,
  Table, useChange, useData, type FormField,
} from "@/components/platform/shared";
import {
  apiRoot, checkbox, choices, enumerated, FieldSection, formData, onOff, options, Pager,
  parseFields, Photo, PhotoPicker, required, resourcePath, Segments, numberField, tableStates,
  value, type Entry, type PageData,
} from "./shared";

type Resource = "categories" | "items" | "areas" | "tables" | "preparation" | "customers" |
  "variants" | "groups" | "modifiers" | "payment-methods";

const descriptions: Record<Resource, { title: string; singular: string; text: string; manage: string; granular?: string }> = {
  categories: { title: "Categorías", singular: "categoría", text: "Organiza tus platillos y controla su orden en el catálogo.", manage: "menu.manage", granular: "categories" },
  items: { title: "Menú", singular: "platillo", text: "Administra el catálogo que utilizará el punto de venta.", manage: "menu.manage", granular: "menu" },
  areas: { title: "Áreas y salones", singular: "área", text: "Organiza los espacios de atención y sus mesas.", manage: "tables.manage" },
  tables: { title: "Mesas", singular: "mesa", text: "Administra capacidad, estados manuales y distribución por salón.", manage: "tables.manage" },
  preparation: { title: "Áreas de preparación", singular: "área de preparación", text: "Define dónde se prepararán los platillos.", manage: "settings.manage" },
  customers: { title: "Clientes", singular: "cliente", text: "Consulta y actualiza los perfiles de tus clientes.", manage: "customers.manage", granular: "customers" },
  variants: { title: "Variantes y tamaños", singular: "variante", text: "Define precios propios o ajustes sobre el precio base.", manage: "menu.manage", granular: "menu" },
  groups: { title: "Extras y modificadores", singular: "grupo de modificadores", text: "Crea grupos reutilizables y define cuántas opciones se pueden elegir.", manage: "menu.manage", granular: "menu" },
  modifiers: { title: "Opciones del grupo", singular: "modificador", text: "Configura los extras y sus incrementos de precio.", manage: "menu.manage", granular: "menu" },
  "payment-methods": { title: "Métodos de pago del restaurante", singular: "método de pago", text: "Prepara los métodos que utilizarán los cobros del restaurante.", manage: "settings.manage" },
};
const description: FormField = { name: "description", label: "Descripción", type: "textarea" };
const named = [required("name", "Nombre"), description, numberField("position", "Orden"), checkbox("active", "Activo")];
const activeItems = enumerated(onOff);
const hasImage = (resource: Resource) => ["categories", "items", "variants"].includes(resource);
const tableStateOptions = enumerated({ available: "Disponible", cleaning: "En limpieza", out_of_service: "Fuera de servicio" });
const choicesQuery = "?size=100&sort=name";

function fieldsFor(resource: Resource, areas: Entry[], categories: Entry[], preparation: Entry[], items: Entry[], groups: Entry[], parent?: string): FormField[] {
  switch (resource) {
    case "categories": return [...named, { name: "icon", label: "Icono" }, { name: "color", label: "Color identificativo" }];
    case "items": return [...named, required("code", "Código interno"), { name: "sku", label: "SKU" },
      options("category_id", "Categoría", choices(categories)), numberField("price_cents", "Precio de venta (Q)", 0, "0.01"),
      numberField("prep_minutes", "Tiempo de preparación (minutos)"),
      options("preparation_id", "Área de preparación", choices(preparation), false), checkbox("available", "Disponible"),
      checkbox("featured", "Destacado")];
    case "variants": return [...named, required("code", "Código interno"),
      ...(parent ? [] : [options("item_id", "Platillo", choices(items))]),
      options("pricing", "Tipo de precio", enumerated({ replace: "Precio propio", adjust: "Ajuste al precio base" })),
      numberField("price_cents", "Precio o ajuste (Q)", -1_000_000, "0.01"), checkbox("available", "Disponible")];
    case "groups": return [...named, numberField("minimum", "Mínimo de opciones"), numberField("maximum", "Máximo de opciones", 1)];
    case "modifiers": return [...named, ...(parent ? [] : [options("group_id", "Grupo", choices(groups))]),
      numberField("price_cents", "Precio adicional (Q)", 0, "0.01")];
    case "tables": return [options("area_id", "Área", choices(areas)), required("number", "Número o código"),
      { name: "name", label: "Nombre" }, numberField("capacity", "Capacidad", 1),
      options("state", "Estado", tableStateOptions), numberField("position", "Orden")];
    case "customers": return [required("name", "Nombre completo"), { name: "tax_id", label: "NIT" },
      { name: "phone", label: "Teléfono" }, { name: "email", label: "Correo electrónico", type: "email" },
      { name: "address", label: "Dirección", type: "textarea" }, { name: "notes", label: "Observaciones", type: "textarea" },
      checkbox("active", "Activo")];
    default: return named;
  }
}

function RecordEditor({ slug, resource, row, parent, permissions, close, done }: {
  slug: string; resource: Resource; row?: Entry; parent?: string; permissions: string[];
  close: () => void; done: () => void;
}) {
  const areas = useData<PageData<Entry>>(resourcePath(slug, "areas") + choicesQuery, resource === "tables");
  const categories = useData<PageData<Entry>>(resourcePath(slug, "categories") + choicesQuery, resource === "items");
  const preparation = useData<PageData<Entry>>(resourcePath(slug, "preparation") + choicesQuery, resource === "items");
  const items = useData<PageData<Entry>>(resourcePath(slug, "items") + choicesQuery, resource === "variants" && !parent);
  const groups = useData<PageData<Entry>>(resourcePath(slug, "groups") + choicesQuery,
    resource === "items" || (resource === "modifiers" && !parent));
  const defaults = useData<{ default_available: boolean; default_area_id: string | null;
    default_preparation_id: string | null }>(`${apiRoot(slug)}/editor-defaults`,
    !row && (resource === "items" || resource === "tables"));
  const [image, setImage] = useState(row ? value(row, "image_id") : "");
  const [selected, setSelected] = useState<string[]>(Array.isArray(row?.group_ids) ? row.group_ids : []);
  const change = useChange(done);
  const fields = fieldsFor(resource, areas.data?.items ?? [], categories.data?.items ?? [],
    preparation.data?.items ?? [], items.data?.items ?? [], groups.data?.items ?? [], parent);
  const initial = {
    position: 0, active: true, available: defaults.data?.default_available ?? true, featured: false, prep_minutes: 0,
    area_id: defaults.data?.default_area_id, preparation_id: defaults.data?.default_preparation_id,
    minimum: 0, maximum: 1, capacity: 4, state: "available", pricing: "replace", ...row,
    price_cents: row ? Number(row.price_cents ?? 0) / 100 : 0,
  };
  const title = `${row ? "Editar" : "Crear"} ${descriptions[resource].singular}`;
  function submit(event: FormEvent<HTMLFormElement>) {
    const body = parseFields(fields, formData(event));
    if (hasImage(resource)) body.image_id = image || null;
    if (resource === "items") body.group_ids = selected;
    if (parent && resource === "variants") body.item_id = parent;
    if (parent && resource === "modifiers") body.group_id = parent;
    const path = resourcePath(slug, resource);
    change.mutate({ path: row ? `${path}/${row.id}` : path, method: row ? "PUT" : "POST", body });
  }
  return <Modal title={title} close={close}>
    {!row && ["items", "tables"].includes(resource) && !defaults.data
      ? <Load error={defaults.error} retry={defaults.refetch} /> : <form onSubmit={submit}>
      {resource === "items" ? <>
        <FieldSection title="Información general"
          fields={fields.filter(({ name }) => !["price_cents", "prep_minutes", "preparation_id"].includes(name))} initial={initial} />
        <FieldSection title="Precios" fields={fields.filter(({ name }) => name === "price_cents")} initial={initial} />
        <fieldset className="restaurant-fieldset"><legend>Variantes y tamaños</legend>
          {row ? <Link className="text-link" href={`/app/${slug}/menu?module=variants&parent=${row.id}`}>Gestionar variantes de este platillo</Link>
            : <p>Las variantes se pueden añadir después de guardar el platillo.</p>}</fieldset>
        <fieldset className="restaurant-fieldset"><legend>Extras y modificadores</legend>
          {groups.data?.items.length ? <div className="commercial-fields">{groups.data.items.map((group) =>
            <label className="check" key={group.id}><input type="checkbox" checked={selected.includes(group.id)}
              onChange={(event) => setSelected(event.target.checked
                ? [...selected, group.id] : selected.filter((id) => id !== group.id))} />{group.name}</label>)}</div> :
            <p>Crea un grupo en Extras y modificadores para poder asociarlo.</p>}
          {panelError(groups.error)}
        </fieldset>
        <FieldSection title="Preparación" fields={fields.filter(({ name }) => ["prep_minutes", "preparation_id"].includes(name))} initial={initial} />
      </> : <Fields fields={fields} initial={initial} />}
      {hasImage(resource) && <PhotoPicker slug={slug} title="Fotografía" selected={image} change={setImage}
        allowed={permissions.includes("media.manage")} />}
      {panelError(change.error || areas.error || categories.error || preparation.error || items.error || groups.error)}
      <Save pending={change.isPending}>{row ? "Guardar cambios" : title}</Save>
    </form>}
  </Modal>;
}

function Batch({ slug, close, done }: { slug: string; close: () => void; done: (data: { count: number }) => void }) {
  const areas = useData<PageData<Entry>>(resourcePath(slug, "areas") + choicesQuery);
  const change = useChange<{ count: number }>(done);
  const fields = [options("area_id", "Área", choices(areas.data?.items)), required("prefix", "Prefijo"),
    numberField("quantity", "Cantidad", 1), numberField("start", "Desde el número", 1), numberField("capacity", "Capacidad", 1)];
  return <Modal title="Crear mesas masivamente" close={close}><form onSubmit={(event) => change.mutate({
    path: `${apiRoot(slug)}/tables/batch`, body: parseFields(fields, formData(event)),
  })}>
    <Fields fields={fields} initial={{ prefix: "Mesa", quantity: 10, start: 1, capacity: 4 }} />
    {panelError(change.error || areas.error)}<Save pending={change.isPending}>Crear mesas</Save>
  </form></Modal>;
}

function Duplicate({ slug, row, close, done }: { slug: string; row: Entry; close: () => void; done: () => void }) {
  const change = useChange(done);
  return <Modal title="Duplicar platillo" close={close}>
    <form onSubmit={(event) => change.mutate({ path: `${apiRoot(slug)}/items/${row.id}/duplicate`,
      body: Object.fromEntries(formData(event)) })}>
      <Fields fields={[required("name", "Nombre del nuevo platillo"), required("code", "Nuevo código interno")]}
        initial={{ name: `${row.name} (copia)`, code: `${value(row, "code")}-copia` }} />
      {panelError(change.error)}<Save pending={change.isPending}>Duplicar</Save>
    </form>
  </Modal>;
}

function Details({ slug, row, resource, close }: { slug: string; row: Entry; resource: Resource; close: () => void }) {
  const history = useData<{ id: string; price_cents: number; pricing: string; created_at: number }[]>(
    `${apiRoot(slug)}/items/${row.id}/prices`, resource === "items");
  return <Modal title={row.name || value(row, "number")} close={close}>
    {resource === "customers" && <div className="commercial-stack">
      <dl className="commercial-summary">{[["NIT", "tax_id"], ["Teléfono", "phone"], ["Correo", "email"],
        ["Dirección", "address"], ["Observaciones", "notes"]].map(([title, key]) =>
        <div key={key}><dt>{title}</dt><dd>{value(row, key) || "—"}</dd></div>)}</dl>
      <h2>Historial de compras</h2><p>Disponible cuando se implemente el registro de ventas.</p>
    </div>}
    {resource === "items" && (history.data ? <Table rows={history.data} rowKey={(item) => item.id} columns={[
      { label: "Fecha", cell: (item) => day(new Date(item.created_at * 1000).toISOString().slice(0, 10)) },
      { label: "Tipo de precio", cell: (item) => ({ base: "Base", replace: "Precio propio", adjust: "Ajuste" }[item.pricing]) },
      { label: "Importe", cell: (item) => money(item.price_cents) },
    ]} /> : <Load error={history.error} retry={history.refetch} />)}
  </Modal>;
}

export function Records({ slug, resource, permissions, initialOpen = false, parent, sub = false }: {
  slug: string; resource: Resource; permissions: string[]; initialOpen?: boolean; parent?: string; sub?: boolean;
}) {
  const config = descriptions[resource];
  const can = (action: string) => restaurantRights(permissions, config.manage, config.granular ? `${config.granular}.${action}` : config.manage);
  const [search, setSearch] = useState("");
  const [active, setActive] = useState("");
  const [area, setArea] = useState("");
  const [category, setCategory] = useState("");
  const [state, setState] = useState("");
  const [available, setAvailable] = useState("");
  const [sort, setSort] = useState("");
  const [page, setPage] = useState(1);
  const [grid, setGrid] = useState(resource === "items" || resource === "tables");
  const [editor, setEditor] = useState<Entry | true | null>(initialOpen && can("create") ? true : null);
  const [duplicate, setDuplicate] = useState<Entry | null>(null);
  const [details, setDetails] = useState<Entry | null>(null);
  const [batch, setBatch] = useState(false);
  const [notice, setNotice] = useState("");
  const query = queryString({ q: useDeferredValue(search), active, category_id: category,
    area_id: area, state, available, sort, page: String(page),
    item_id: resource === "variants" ? parent ?? "" : "", group_id: resource === "modifiers" ? parent ?? "" : "" });
  const results = useData<PageData<Entry>>(`${resourcePath(slug, resource)}?${query}`);
  const areas = useData<PageData<Entry>>(resourcePath(slug, "areas") + choicesQuery, resource === "tables");
  const categories = useData<PageData<Entry>>(resourcePath(slug, "categories") + choicesQuery, resource === "items");
  const change = useChange(() => { setNotice("Registro actualizado."); });
  const areaName = (key: string) => areas.data?.items.find((area) => area.id === key)?.name ?? "Área";
  const categoryName = (key: string) => categories.data?.items.find((category) => category.id === key)?.name ?? "Categoría";
  const name = (row: Entry) => resource === "tables" ? [row.number, row.name].filter(Boolean).join(" · ") : row.name;
  const statePill = (row: Entry) => resource === "tables" ? <span className={`status table-state-${value(row, "state")}`}>
    <i />{tableStates[value(row, "state")]}</span> : <Pill value={row.active === false ? "Inactivo" : "active"} />;
  const availability = (row: Entry) => row.active === false ? "Inactivo" : row.available ? "Disponible" : "Agotado";
  function changeFilter(set: (value: string) => void, value: string) { set(value); setPage(1); }
  function quickAvailability(row: Entry) {
    const fields = fieldsFor("items", [], [], [], [], []);
    const body = Object.fromEntries(fields.map(({ name }) => [name, row[name]]));
    change.mutate({ path: `${resourcePath(slug, "items")}/${row.id}`, method: "PUT",
      body: { ...body, group_ids: row.group_ids, image_id: row.image_id, available: !row.available } });
  }
  const actions = (row: Entry) => <div className="commercial-actions">
    {can("edit") && <Button variant="outline" onClick={() => setEditor(row)}>Editar</Button>}
    {resource === "items" && <>
      {can("edit") && row.active !== false && <Button variant="ghost" disabled={change.isPending} onClick={() => quickAvailability(row)}>
        {row.available ? "Marcar agotado" : "Marcar disponible"}</Button>}
      {permissions.includes("menu.manage") && <><Button variant="ghost" onClick={() => setDetails(row)}>Precios</Button>
        <Button variant="ghost" onClick={() => setDuplicate(row)}>Duplicar</Button></>}
    </>}
    {resource === "groups" && <Button variant="ghost" asChild><Link href={`/app/${slug}/menu?module=modifiers&parent=${row.id}`}>Gestionar opciones</Link></Button>}
    {resource === "customers" && <Button variant="ghost" onClick={() => setDetails(row)}>Ver perfil</Button>}
    {can("archive") && row.active !== false && <Button variant="ghost" disabled={change.isPending} onClick={() => {
      if (window.confirm(resource === "tables" ? "¿Eliminar esta mesa?" : "¿Archivar este registro?"))
        change.mutate({ path: `${resourcePath(slug, resource)}/${row.id}`, method: "DELETE" });
    }}>{resource === "tables" ? "Eliminar" : "Archivar"}</Button>}
  </div>;
  const rows = results.data?.items ?? [];
  const groupKeys = [...new Set(rows.map((row) => value(row, "area_id")))];
  const cards = (items: Entry[]) => <div className="restaurant-card-grid">{items.map((row) =>
    <article className="panel restaurant-card" key={row.id}>
      {resource === "items" && <Photo slug={slug} id={value(row, "image_id")} alt={`Foto de ${row.name}`} />}
      <div className="restaurant-card-body">
        <div className="commercial-row"><h2>{resource === "tables" && <Armchair size={19} />}{name(row)}</h2>{statePill(row)}</div>
        {resource === "items" && <p>{categoryName(value(row, "category_id"))} · {money(Number(row.price_cents))} · {availability(row)}</p>}
        {resource === "tables" && <p>{areaName(value(row, "area_id"))} · Capacidad {value(row, "capacity")}</p>}
        {actions(row)}
      </div>
    </article>)}</div>;
  return <>
    {sub ? <h2>{config.title}</h2> : <Heading title={config.title} text={config.text} action={can("create") &&
      <NewButton onClick={() => setEditor(true)}>{resource === "items" ? "Agregar platillo" : `Crear ${config.singular}`}</NewButton>} />}
    {sub && can("create") && <div className="export-actions"><NewButton onClick={() => setEditor(true)}>Crear {config.singular}</NewButton></div>}
    <div className="commercial-actions export-actions">
      {resource === "tables" && <>
        <Button asChild variant="outline"><Link href={`/app/${slug}/areas`}>Áreas y salones</Link></Button>
        {can("create") && <Button variant="outline" onClick={() => setBatch(true)}>Crear mesas masivamente</Button>}
      </>}
      {resource === "customers" && permissions.includes("customers.export") && <Button asChild variant="outline">
        <a href={`/api${apiRoot(slug)}/customers/export`}>Exportar clientes</a></Button>}
      {["items", "tables"].includes(resource) && <>
        <Button type="button" variant={grid ? "outline" : "ghost"} aria-pressed={grid} onClick={() => setGrid(true)}><Grid2X2 size={18} /> Cuadrícula</Button>
        <Button type="button" variant={!grid ? "outline" : "ghost"} aria-pressed={!grid} onClick={() => setGrid(false)}><List size={18} /> Tabla</Button>
      </>}
    </div>
    <Note>{notice}</Note>{panelError(change.error)}
    <div className="panel commercial-filters restaurant-filters">
      <label>Buscar<input type="search" value={search} maxLength={100} onChange={(event) => changeFilter(setSearch, event.target.value)} /></label>
      <label>Ordenar<select value={sort} onChange={(event) => changeFilter(setSort, event.target.value)}>
        <option value="">Orden predeterminado</option><option value="name">Nombre</option><option value="recent">Recientes</option>
        {resource === "items" && <option value="price">Precio</option>}
      </select></label>
      {["categories", "items", "areas", "preparation", "groups", "customers"].includes(resource) && <label>Estado<select
        value={active} onChange={(event) => changeFilter(setActive, event.target.value)}>
        <option value="">Todos</option>{activeItems.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
      </select></label>}
      {resource === "items" && <>
        <label>Categoría<select value={category} onChange={(event) => changeFilter(setCategory, event.target.value)}>
          <option value="">Todas</option>{categories.data?.items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select></label>
        <label>Disponibilidad<select value={available} onChange={(event) => changeFilter(setAvailable, event.target.value)}>
          <option value="">Todas</option><option value="true">Disponible</option><option value="false">Agotado</option>
        </select></label>
      </>}
      {resource === "tables" && <>
        <label>Área<select value={area} onChange={(event) => changeFilter(setArea, event.target.value)}>
          <option value="">Todas</option>{areas.data?.items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select></label>
        <label>Estado<select value={state} onChange={(event) => changeFilter(setState, event.target.value)}>
          <option value="">Todos</option>{enumerated(tableStates).map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
        </select></label>
      </>}
    </div>
    {results.data ? (grid && rows.length ? (resource === "tables" ? <div className="commercial-stack">
      {groupKeys.map((key) => <section key={key} className="commercial-stack"><h2>{areaName(key)}</h2>
        {cards(rows.filter((row) => value(row, "area_id") === key))}</section>)}</div> : cards(rows)) :
      <Table rows={rows} rowKey={(row) => row.id} columns={[
        ...(resource === "items" ? [{ label: "Foto", cell: (row: Entry) => <Photo slug={slug} id={value(row, "image_id")} alt="" className="restaurant-thumbnail" /> },
          { label: "Código", cell: (row: Entry) => value(row, "code") }] : []),
        { label: resource === "tables" ? "Mesa" : "Nombre", cell: name },
        ...(["categories", "areas"].includes(resource) ? [{ label: "Asociados", cell: (row: Entry) => value(row, "associated") }] : []),
        ...(resource === "tables" ? [{ label: "Área", cell: (row: Entry) => areaName(value(row, "area_id")) },
          { label: "Capacidad", cell: (row: Entry) => value(row, "capacity") }] : []),
        ...(resource === "items" ? [{ label: "Categoría", cell: (row: Entry) => categoryName(value(row, "category_id")) },
          { label: "Disponibilidad", cell: availability }] : []),
        ...(["items", "variants", "modifiers"].includes(resource) ? [{ label: "Precio", cell: (row: Entry) => money(Number(row.price_cents)) }] : []),
        ...(resource === "groups" ? [{ label: "Selección", cell: (row: Entry) =>
          `${Number(row.minimum) ? "Obligatoria" : "Opcional"} · ${value(row, "minimum")}/${value(row, "maximum")} · ${Number(row.maximum) === 1 ? "Única" : "Múltiple"}` }] : []),
        ...(resource === "customers" ? [{ label: "NIT", cell: (row: Entry) => value(row, "tax_id") },
          { label: "Teléfono", cell: (row: Entry) => value(row, "phone") }] : []),
        { label: "Estado", cell: statePill }, { label: "Acciones", cell: actions },
      ]} />) : <Load error={results.error} retry={results.refetch} />}
    {results.data && <Pager total={results.data.total} page={page} setPage={setPage} />}
    {editor && <RecordEditor slug={slug} resource={resource} parent={parent} permissions={permissions}
      row={editor === true ? undefined : editor} close={() => setEditor(null)}
      done={() => { setEditor(null); setNotice("Registro guardado."); }} />}
    {batch && <Batch slug={slug} close={() => setBatch(false)}
      done={(result) => { setBatch(false); setNotice(`Se crearon ${result.count} mesas.`); }} />}
    {duplicate && <Duplicate slug={slug} row={duplicate} close={() => setDuplicate(null)}
      done={() => { setDuplicate(null); setNotice("Platillo duplicado."); }} />}
    {details && <Details slug={slug} row={details} resource={resource} close={() => setDetails(null)} />}
  </>;
}

const modules: Record<string, Resource> = { items: "items", variants: "variants", groups: "groups", modifiers: "modifiers", preparation: "preparation" };

export function MenuView({ slug, permissions, section, parent, initialOpen }: {
  slug: string; permissions: string[]; section?: string; parent?: string; initialOpen: boolean;
}) {
  const initial = modules[section ?? ""] ?? "items";
  const [resource, setResource] = useState<Resource>(initial);
  const views: Resource[] = ["items", "variants", "groups", "modifiers", "preparation"];
  const titles = views.map((view) => descriptions[view].title);
  return <>
    <Heading title="Menú del restaurante" text="Organiza los platillos, sus opciones y áreas de preparación."
      action={<SlidersHorizontal size={24} />} />
    <Segments label="Módulos del menú" values={titles} selected={descriptions[resource].title}
      change={(value) => setResource(views[titles.indexOf(value)])} />
    <Records key={`${resource}-${section}-${parent}`} slug={slug} resource={resource} permissions={permissions}
      parent={resource === initial ? parent : undefined} initialOpen={resource === initial && initialOpen} sub />
  </>;
}
