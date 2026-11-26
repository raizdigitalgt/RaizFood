"use client";

import { FolderPlus, FolderOpen, Grid2X2, List, Upload } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useDeferredValue, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  errorText, Fields, Heading, Load, Modal, Note, panelError, queryString, Save, Table, useChange, useData,
} from "@/components/platform/shared";
import {
  apiRoot, choices, formData, mediaUrl, options, Pager, parseFields, Photo, required, resourcePath,
  uploadPhoto, type Folder, type MediaFile, type PageData,
} from "./shared";

type Selection = { kind: "folders"; record?: Folder } | { kind: "files"; record: MediaFile };

function Editor({ slug, selection, current, folders, close, done }: {
  slug: string; selection: Selection; current: string | null; folders: Folder[];
  close: () => void; done: () => void;
}) {
  const { kind, record } = selection;
  const change = useChange(done);
  const parent = kind === "folders" ? "parent_id" : "folder_id";
  const fields = [required("name", kind === "folders" ? "Nombre de carpeta" : "Nombre del archivo"),
    options(parent, "Carpeta superior", [{ value: "", label: "Biblioteca" },
      ...choices(folders.filter((folder) => folder.id !== record?.id))].filter((row) => row.value), false)];
  const title = kind === "files" ? "Detalles de la imagen" : record ? "Editar carpeta" : "Nueva carpeta";
  return <Modal title={title} close={close}>
    {selection.kind === "files" && <div className="commercial-stack">
      <Photo slug={slug} id={selection.record.id} alt={selection.record.name} />
      <p>{selection.record.width} × {selection.record.height} px · {Math.ceil(selection.record.size / 1024)} KiB</p>
      <a className="text-link" href={mediaUrl(slug, selection.record.id, false)} target="_blank" rel="noreferrer">Abrir imagen optimizada</a>
    </div>}
    <form onSubmit={(event) => {
      const base = resourcePath(slug, kind);
      change.mutate({ path: record ? `${base}/${record.id}` : base,
        method: record ? "PUT" : "POST", body: parseFields(fields, formData(event)) });
    }}>
      <Fields fields={fields} initial={record ? { ...record } : { [parent]: current }} />
      {panelError(change.error)}<Save pending={change.isPending}>{record ? "Guardar cambios" : "Crear carpeta"}</Save>
    </form>
  </Modal>;
}

function UploadDialog({ slug, folder, close, done }: {
  slug: string; folder: string | null; close: () => void; done: (count: number) => void;
}) {
  const limit = useData<{ max_bytes: number }>(`${apiRoot(slug)}/media/limits`);
  const cache = useQueryClient();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  return <Modal title="Subir fotografías" close={close}>
    <form onSubmit={async (event) => {
      const files = formData(event).getAll("photos").filter((item): item is File => item instanceof File && item.size > 0);
      let uploaded = 0;
      setPending(true); setError("");
      const failed = [];
      for (const file of files) {
        try { await uploadPhoto(slug, file, folder, limit.data?.max_bytes ?? 8_388_608); uploaded++; }
        catch (reason) { failed.push(`${file.name}: ${errorText(reason)}`); }
      }
      setPending(false);
      void cache.invalidateQueries({ queryKey: ["commercial"] });
      if (failed.length) setError(`${uploaded} imágenes guardadas. ${failed.join(" ")}`);
      else done(uploaded);
    }}>
      <label className="field">Fotografías<input name="photos" type="file" multiple required
        accept="image/jpeg,image/png,image/webp,image/avif" disabled={pending} /></label>
      <p>JPG, PNG, WebP o AVIF · hasta {Math.round((limit.data?.max_bytes ?? 8_388_608) / 1_048_576)} MB por archivo.</p>
      {error && <p role="alert" className="field-error">{error}</p>}
      <Save pending={pending}>Subir archivos</Save>
    </form>
  </Modal>;
}

export function Media({ slug, initialOpen }: { slug: string; initialOpen: boolean }) {
  const [trail, setTrail] = useState<Folder[]>([]);
  const [search, setSearch] = useState("");
  const [scope, setScope] = useState("");
  const [grid, setGrid] = useState(true);
  const [page, setPage] = useState(1);
  const [edit, setEdit] = useState<Selection | null>(null);
  const [upload, setUpload] = useState(initialOpen);
  const [notice, setNotice] = useState("");
  const current = trail.at(-1)?.id ?? null;
  const q = useDeferredValue(search);
  const baseFolders = useData<PageData<Folder>>(`${resourcePath(slug, "folders")}?size=100&sort=name`);
  const directories = useData<PageData<Folder>>(`${resourcePath(slug, "folders")}?${queryString({
    parent_id: current ?? "root", size: "100", sort: "name",
  })}`);
  const photos = useData<PageData<MediaFile>>(`${resourcePath(slug, "files")}?${queryString({
    folder_id: scope === "all" ? "" : current ?? "root", q, page: String(page), sort: "recent",
  })}`);
  const remove = useChange(() => { setEdit(null); setNotice("Registro eliminado."); });
  function navigate(folders: Folder[]) {
    setTrail(folders); setPage(1); setSearch(""); setScope("");
  }
  function erase(kind: Selection["kind"], id: string) {
    if (window.confirm(kind === "folders" ? "¿Eliminar esta carpeta vacía?" : "¿Eliminar esta imagen?"))
      remove.mutate({ path: `${resourcePath(slug, kind)}/${id}`, method: "DELETE" });
  }
  return <>
    <Heading title="Multimedia" text="Organiza las fotografías que utiliza tu restaurante."
      action={<div className="commercial-actions">
        <Button variant="outline" onClick={() => setEdit({ kind: "folders" })}><FolderPlus size={18} /> Nueva carpeta</Button>
        <Button onClick={() => setUpload(true)}><Upload size={18} /> Subir archivos</Button>
      </div>} />
    <Note>{notice}</Note>{panelError(remove.error)}
    <nav className="commercial-actions export-actions" aria-label="Ruta de carpetas">
      <Button variant={trail.length ? "ghost" : "outline"} onClick={() => navigate([])}>Biblioteca</Button>
      {trail.map((folder, index) => <span key={folder.id}> / <Button variant="ghost" aria-current={index === trail.length - 1 ? "page" : undefined}
        onClick={() => navigate(trail.slice(0, index + 1))}>{folder.name}</Button></span>)}
    </nav>
    {directories.data ? <div className="restaurant-folder-grid export-actions">{directories.data.items.map((folder) =>
      <article className="panel commercial-inset commercial-stack" key={folder.id}>
        <Button variant="ghost" onClick={() => navigate([...trail, folder])}><FolderOpen size={19} /> {folder.name}</Button>
        <div className="commercial-actions">
          <Button variant="outline" onClick={() => setEdit({ kind: "folders", record: folder })}>Editar</Button>
          <Button variant="ghost" disabled={remove.isPending} onClick={() => erase("folders", folder.id)}>Eliminar</Button>
        </div>
      </article>)}</div> : <Load error={directories.error} retry={directories.refetch} />}
    <div className="panel commercial-filters">
      <label>Buscar fotografías<input type="search" value={search} maxLength={100}
        onChange={(event) => { setSearch(event.target.value); setPage(1); }} /></label>
      <label>Buscar en<select value={scope} onChange={(event) => { setScope(event.target.value); setPage(1); }}>
        <option value="">Carpeta actual</option><option value="all">Toda la biblioteca</option>
      </select></label>
      <Button variant={grid ? "outline" : "ghost"} aria-pressed={grid} onClick={() => setGrid(true)}><Grid2X2 size={18} /> Cuadrícula</Button>
      <Button variant={!grid ? "outline" : "ghost"} aria-pressed={!grid} onClick={() => setGrid(false)}><List size={18} /> Lista</Button>
    </div>
    {photos.data ? <>
      {grid && photos.data.items.length ? <div className="restaurant-card-grid">{photos.data.items.map((row) =>
        <article key={row.id} className="panel restaurant-card">
          <Photo slug={slug} id={row.id} alt={row.name} />
          <div className="restaurant-card-body"><h2>{row.name}</h2><p>{row.width} × {row.height} px</p>
            <div className="commercial-actions">
              <Button variant="outline" onClick={() => setEdit({ kind: "files", record: row })}>Detalles</Button>
              <Button variant="ghost" disabled={remove.isPending} onClick={() => erase("files", row.id)}>Eliminar</Button>
            </div>
          </div>
        </article>)}</div>
        : <Table rows={photos.data.items} rowKey={(row) => row.id} columns={[
          { label: "Imagen", cell: (row) => <Photo slug={slug} id={row.id} alt="" className="restaurant-thumbnail" /> },
          { label: "Nombre", cell: (row) => row.name }, { label: "Dimensiones", cell: (row) => `${row.width} × ${row.height} px` },
          { label: "Tamaño", cell: (row) => `${Math.ceil(row.size / 1024)} KiB` },
          { label: "Acciones", cell: (row) => <div className="commercial-actions">
            <Button variant="outline" onClick={() => setEdit({ kind: "files", record: row })}>Detalles</Button>
            <Button variant="ghost" disabled={remove.isPending} onClick={() => erase("files", row.id)}>Eliminar</Button></div> },
        ]} />}
      <Pager page={page} total={photos.data.total} setPage={setPage} />
    </> : <Load error={photos.error} retry={photos.refetch} />}
    {edit && <Editor slug={slug} selection={edit} current={current} folders={baseFolders.data?.items ?? []}
      close={() => setEdit(null)} done={() => { setEdit(null); setNotice("Cambios guardados."); }} />}
    {upload && <UploadDialog slug={slug} folder={current} close={() => setUpload(false)} done={(count) => {
      setUpload(false); setNotice(`${count} imágenes guardadas.`);
    }} />}
  </>;
}
