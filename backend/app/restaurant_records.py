from dataclasses import dataclass
from typing import Annotated
from unicodedata import normalize

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import delete, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError

from app import restaurant_models as m
from app import restaurant_schemas as s
from app.access import audit
from app.auth import DB
from app.db import write_transaction
from app.models import now, uuid
from app.operations import restaurant_user

router = APIRouter(prefix="/restaurants/{slug}", tags=["Administración del restaurante"])


@dataclass(frozen=True)
class Resource:
    table: object
    schema: type
    read: str
    write: str
    references: tuple = ()
    filters: tuple = ()
    search: tuple = ("name",)


MENU = ("menu.view", "menu.manage")
TABLES = ("tables.view", "tables.manage")
RESOURCES = {
    "categories": Resource(
        m.categories, s.Category, *MENU, (("image_id", m.media_files),), ("active",)
    ),
    "items": Resource(
        m.items,
        s.MenuItem,
        *MENU,
        (
            ("category_id", m.categories),
            ("image_id", m.media_files),
            ("preparation_id", m.preparation),
        ),
        ("active", "available", "category_id"),
        ("name", "code", "sku"),
    ),
    "variants": Resource(
        m.variants,
        s.Variant,
        *MENU,
        (("item_id", m.items), ("image_id", m.media_files)),
        ("item_id", "active"),
    ),
    "groups": Resource(m.groups, s.Group, *MENU, filters=("active",)),
    "modifiers": Resource(m.modifiers, s.Modifier, *MENU, (("group_id", m.groups),), ("group_id",)),
    "areas": Resource(m.areas, s.Named, *TABLES, filters=("active",)),
    "tables": Resource(
        m.tables,
        s.RestaurantTable,
        *TABLES,
        (("area_id", m.areas),),
        ("area_id", "state"),
        ("number", "name"),
    ),
    "preparation": Resource(
        m.preparation, s.Named, "menu.view", "settings.manage", filters=("active",)
    ),
    "customers": Resource(
        m.customers,
        s.Customer,
        "customers.manage",
        "customers.manage",
        filters=("active",),
        search=("name", "tax_id", "phone", "email"),
    ),
    "folders": Resource(
        m.media_folders,
        s.Folder,
        "media.manage",
        "media.manage",
        (("parent_id", m.media_folders),),
        ("parent_id",),
    ),
    "files": Resource(
        m.media_files,
        s.FileEdit,
        "media.manage",
        "media.manage",
        (("folder_id", m.media_folders),),
        ("folder_id",),
    ),
    "payment-methods": Resource(
        m.payment_methods, s.Named, "settings.manage", "settings.manage", filters=("active",)
    ),
}
ARCHIVED = {
    "categories",
    "items",
    "variants",
    "groups",
    "modifiers",
    "areas",
    "preparation",
    "customers",
    "payment-methods",
}


def normalized(value):
    return " ".join(normalize("NFKC", value).casefold().split())


GRANULAR = {
    "categories": "categories",
    "items": "menu",
    "variants": "menu",
    "groups": "menu",
    "modifiers": "menu",
    "customers": "customers",
}


def record_access(request, db, slug, resource, action="view"):
    info = resource_for(resource)
    actor, access = restaurant_user(request, db, slug, None)
    fallback = info.read if action == "view" else info.write
    granular = GRANULAR.get(resource)
    view_alternative = action == "view" and (
        info.write in access.permissions
        or (resource == "areas" and "settings.manage" in access.permissions)
    )
    if (
        not view_alternative
        and fallback not in access.permissions
        and (not granular or f"{granular}.{action}" not in access.permissions)
    ):
        raise HTTPException(403, "Permiso insuficiente")
    return actor, access


def resource_for(key):
    if key not in RESOURCES:
        raise HTTPException(404, "Recurso no disponible")
    return RESOURCES[key]


def projection(table):
    return [
        col
        for col in table.c
        if col.name not in {"tenant_id", "content", "thumbnail"}
        and not col.name.startswith("normalized_")
    ]


def condition(table, tenant_id, key=None):
    scope = table.c.tenant_id == tenant_id
    return scope if key is None else scope & (table.c.id == key)


def scoped_rows(db, table, tenant_id):
    return select(*projection(table)).where(condition(table, tenant_id))


def get_row(db, table, tenant_id, key):
    row = db.execute(scoped_rows(db, table, tenant_id).where(table.c.id == key)).mappings().first()
    if not row:
        raise HTTPException(404, "Registro no disponible")
    return dict(row)


def payload(schema, value):
    try:
        return schema.model_validate(value).model_dump(mode="json")
    except ValidationError as error:
        raise RequestValidationError(error.errors()) from error


def enrich(db, key, tenant_id, rows):
    if not rows:
        return rows
    ids = [row["id"] for row in rows]
    if key == "items":
        pairs = db.execute(
            select(m.item_groups.c.item_id, m.item_groups.c.group_id).where(
                m.item_groups.c.tenant_id == tenant_id, m.item_groups.c.item_id.in_(ids)
            )
        )
        grouped = {row_id: [] for row_id in ids}
        for item_id, group_id in pairs:
            grouped[item_id].append(group_id)
        for row in rows:
            row["group_ids"] = grouped[row["id"]]
    elif key in {"categories", "areas"}:
        child, field = (
            (m.items, m.items.c.category_id)
            if key == "categories"
            else (m.tables, m.tables.c.area_id)
        )
        counts = dict(
            db.execute(
                select(field, func.count())
                .where(
                    condition(child, tenant_id),
                    field.in_(ids),
                )
                .group_by(field)
            )
            .tuples()
            .all()
        )
        for row in rows:
            row["associated"] = counts.get(row["id"], 0)
    return rows


def browsing(db, resource, key, tenant_id, params, q, page, limit):
    table = resource.table
    conditions = [condition(table, tenant_id)]
    if q:
        conditions.append(
            or_(*(table.c[name].icontains(q, autoescape=True) for name in resource.search))
        )
    for field in resource.filters:
        value = params.get(field)
        if value is None or value == "":
            continue
        if field in {"available", "active"}:
            if value not in {"true", "false"}:
                raise HTTPException(422, "Filtro inválido")
            conditions.append(table.c[field].is_(value == "true"))
        elif field in {"parent_id", "folder_id"} and value == "root":
            conditions.append(table.c[field].is_(None))
        else:
            conditions.append(table.c[field] == value)
    sort = params.get("sort")
    columns = {"name": table.c.name, "recent": table.c.created_at.desc()}
    if "price_cents" in table.c:
        columns["price"] = table.c.price_cents
    default = table.c.position if "position" in table.c else table.c.name
    query = (
        select(*projection(table))
        .where(*conditions)
        .order_by(columns.get(sort, default), table.c.name, table.c.id)
    )
    rows = db.execute(query.offset((page - 1) * limit).limit(limit)).mappings()
    count = db.scalar(select(func.count()).select_from(table).where(*conditions))
    return {"items": enrich(db, key, tenant_id, [dict(row) for row in rows]), "total": count}


def references(db, resource, tenant_id, data):
    for field, table in resource.references:
        key = data.get(field)
        if key:
            get_row(db, table, tenant_id, key)


def folder_cycle(db, tenant_id, key, parent):
    seen = {key}
    while parent:
        if parent in seen:
            raise HTTPException(409, "La carpeta no puede contenerse a sí misma")
        seen.add(parent)
        parent = get_row(db, m.media_folders, tenant_id, parent)["parent_id"]


def record(db, resource_key, tenant_id, actor, data, key=None):
    resource = resource_for(resource_key)
    table = resource.table
    previous = get_row(db, table, tenant_id, key) if key else None
    if (
        previous
        and resource_key == "tables"
        and previous["state"]
        not in {
            "available",
            "cleaning",
            "out_of_service",
        }
    ):
        raise HTTPException(409, "La mesa está en uso operativo")
    if previous and resource_key in {"variants", "modifiers"}:
        parent = "item_id" if resource_key == "variants" else "group_id"
        if previous[parent] != data[parent]:
            raise HTTPException(409, "El registro debe conservar su vínculo original")
    references(db, resource, tenant_id, data)
    key = key or uuid()
    if resource_key == "folders":
        folder_cycle(db, tenant_id, key, data.get("parent_id"))
    group_ids = data.pop("group_ids", None)
    if group_ids is not None:
        group_ids = list(dict.fromkeys(group_ids))
        if group_ids:
            found = db.scalar(
                select(func.count())
                .select_from(m.groups)
                .where(
                    condition(m.groups, tenant_id),
                    m.groups.c.id.in_(group_ids),
                )
            )
            if found != len(group_ids):
                raise HTTPException(404, "Grupo no disponible")
        invalid = db.scalar(
            select(m.variants.c.id)
            .where(
                condition(m.variants, tenant_id),
                m.variants.c.item_id == key,
                m.variants.c.pricing == "adjust",
                m.variants.c.price_cents < -data["price_cents"],
            )
            .limit(1)
        )
        if invalid:
            raise HTTPException(422, "Una variante quedaría con precio negativo")
    if resource_key == "variants" and data["pricing"] == "adjust":
        item = get_row(db, m.items, tenant_id, data["item_id"])
        if item["price_cents"] + data["price_cents"] < 0:
            raise HTTPException(422, "La variante quedaría con precio negativo")
    for field in ("name", "number", "code"):
        if f"normalized_{field}" in table.c:
            data[f"normalized_{field}"] = normalized(data[field])
    claimed = {**data, "updated_at": now()}
    if previous:
        db.execute(update(table).where(condition(table, tenant_id, key)).values(**claimed))
    else:
        db.execute(insert(table).values(id=key, tenant_id=tenant_id, **claimed))
    if group_ids is not None:
        db.execute(
            delete(m.item_groups).where(
                m.item_groups.c.tenant_id == tenant_id, m.item_groups.c.item_id == key
            )
        )
        if group_ids:
            db.execute(
                insert(m.item_groups),
                [
                    {"tenant_id": tenant_id, "item_id": key, "group_id": group_id}
                    for group_id in group_ids
                ],
            )
    if resource_key in {"items", "variants"}:
        pricing = data.get("pricing", "base")
        if not previous or (previous["price_cents"], previous.get("pricing", "base")) != (
            data["price_cents"],
            pricing,
        ):
            db.execute(
                insert(m.price_history).values(
                    tenant_id=tenant_id,
                    item_id=data.get("item_id", key),
                    variant_id=key if resource_key == "variants" else None,
                    actor_id=actor.id,
                    price_cents=data["price_cents"],
                    pricing=pricing,
                )
            )
            if previous:
                audit(db, actor, "restaurant.menu.price", key, tenant_id)
        if previous and previous["available"] != data["available"]:
            audit(db, actor, "restaurant.menu.availability", key, tenant_id)
    audit(
        db, actor, f"restaurant.{resource_key}.{'edit' if previous else 'create'}", key, tenant_id
    )
    return enrich(db, resource_key, tenant_id, [get_row(db, table, tenant_id, key)])[0]


@router.get("/records/{resource}")
def list_records(
    slug: str,
    resource: str,
    request: Request,
    db: DB,
    q: Annotated[str, Query(max_length=100)] = "",
    page: Annotated[int, Query(ge=1, le=10000)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    info = resource_for(resource)
    _, access = record_access(request, db, slug, resource)
    return browsing(db, info, resource, access.tenant.id, request.query_params, q, page, size)


@router.get("/records/{resource}/{key}")
def read_record(slug: str, resource: str, key: str, request: Request, db: DB):
    info = resource_for(resource)
    _, access = record_access(request, db, slug, resource)
    rows = [get_row(db, info.table, access.tenant.id, key)]
    return enrich(db, resource, access.tenant.id, rows)[0]


def write_record(slug, resource, request, db, raw, key=None):
    info = resource_for(resource)
    if resource == "files" and not key:
        raise HTTPException(405, "Utiliza la biblioteca para subir archivos")
    try:
        with write_transaction(db):
            actor, access = record_access(request, db, slug, resource, "edit" if key else "create")
            values = payload(info.schema, raw)
            if resource == "items" and not key and "available" not in raw:
                preferences = (
                    db.scalar(
                        select(m.settings.c.preferences).where(
                            m.settings.c.tenant_id == access.tenant.id
                        )
                    )
                    or {}
                )
                values["available"] = preferences.get("default_available", True)
            return record(db, resource, access.tenant.id, actor, values, key)
    except IntegrityError as error:
        raise HTTPException(409, "Ya existe un registro con ese nombre o código") from error


@router.post("/records/{resource}", status_code=201)
def create_record(slug: str, resource: str, request: Request, db: DB, data: dict):
    return write_record(slug, resource, request, db, data)


@router.put("/records/{resource}/{key}")
def replace_record(slug: str, resource: str, key: str, request: Request, db: DB, data: dict):
    return write_record(slug, resource, request, db, data, key)


@router.delete("/records/{resource}/{key}", status_code=204)
def remove_record(slug: str, resource: str, key: str, request: Request, db: DB):
    info = resource_for(resource)
    table = info.table
    try:
        with write_transaction(db):
            actor, access = record_access(request, db, slug, resource, "archive")
            tenant_id = access.tenant.id
            row = get_row(db, table, tenant_id, key)
            if resource in ARCHIVED:
                db.execute(
                    update(table)
                    .where(condition(table, tenant_id, key))
                    .values(active=False, updated_at=now())
                )
            else:
                if resource == "tables" and row["state"] not in {
                    "available",
                    "cleaning",
                    "out_of_service",
                }:
                    raise HTTPException(409, "La mesa está en uso operativo")
                db.execute(delete(table).where(condition(table, tenant_id, key)))
            audit(
                db,
                actor,
                f"restaurant.{resource}.{'archive' if resource in ARCHIVED else 'delete'}",
                key,
                tenant_id,
            )
    except IntegrityError as error:
        raise HTTPException(409, "El registro sigue vinculado a otros recursos") from error
    return Response(status_code=204)


@router.post("/tables/batch", status_code=201)
def create_batch(slug: str, data: s.BatchTables, request: Request, db: DB):
    try:
        with write_transaction(db):
            actor, access = restaurant_user(request, db, slug, "tables.manage")
            tenant = access.tenant.id
            get_row(db, m.areas, tenant, data.area_id)
            rows = []
            for number in range(data.start, data.start + data.quantity):
                name = f"{data.prefix} {number:02d}"
                row = {
                    "id": uuid(),
                    "tenant_id": tenant,
                    "area_id": data.area_id,
                    "number": name,
                    "normalized_number": normalized(name),
                    "capacity": data.capacity,
                    "state": "available",
                    "position": number,
                }
                rows.append(row)
            db.execute(insert(m.tables), rows)
            for row in rows:
                audit(db, actor, "restaurant.tables.create", row["id"], tenant)
            return {"count": len(rows)}
    except IntegrityError as error:
        raise HTTPException(409, "El lote contiene un número de mesa existente") from error


@router.post("/items/{key}/duplicate", status_code=201)
def duplicate(slug: str, key: str, data: s.DuplicateItem, request: Request, db: DB):
    try:
        with write_transaction(db):
            actor, access = restaurant_user(request, db, slug, "menu.manage")
            tenant = access.tenant.id
            item = enrich(db, "items", tenant, [get_row(db, m.items, tenant, key)])[0]
            item = {field: item[field] for field in s.MenuItem.model_fields}
            item.update(data.model_dump())
            result = record(db, "items", tenant, actor, item)
            originals = (
                db.execute(scoped_rows(db, m.variants, tenant).where(m.variants.c.item_id == key))
                .mappings()
                .all()
            )
            for index, variant in enumerate(originals, start=1):
                copy = {field: variant[field] for field in s.Variant.model_fields}
                copy.update(item_id=result["id"], code=f"{data.code[:58]}-{index:02d}")
                record(db, "variants", tenant, actor, copy)
            return result
    except IntegrityError as error:
        raise HTTPException(409, "El código de un platillo o de su variante ya existe") from error


@router.get("/items/{key}/prices")
def prices(slug: str, key: str, request: Request, db: DB):
    _, access = restaurant_user(request, db, slug, "menu.manage")
    tenant = access.tenant.id
    get_row(db, m.items, tenant, key)
    return [
        dict(row)
        for row in db.execute(
            scoped_rows(db, m.price_history, tenant)
            .where(m.price_history.c.item_id == key)
            .order_by(m.price_history.c.created_at.desc())
        ).mappings()
    ]
