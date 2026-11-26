import csv
from collections import Counter, defaultdict
from io import StringIO

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select

from app import restaurant_models as m
from app.auth import DB
from app.operations import restaurant_user
from app.platform_reporting import csv_cell
from app.restaurant_records import condition, get_row, scoped_rows
from app.restaurant_schemas import Quote

router = APIRouter(prefix="/restaurants/{slug}", tags=["Catálogo operativo"])


def catalog(db, tenant):
    def active(table, *filters):
        return [
            dict(row)
            for row in db.execute(
                scoped_rows(db, table, tenant)
                .where(table.c.active, *filters)
                .order_by(table.c.position, table.c.name, table.c.id)
            ).mappings()
        ]

    categories = active(m.categories)
    items = active(m.items, m.items.c.category_id.in_([row["id"] for row in categories]))
    ids = [row["id"] for row in items]
    extras = active(m.groups)
    option_rows = active(m.modifiers, m.modifiers.c.group_id.in_([row["id"] for row in extras]))
    options = defaultdict(list)
    for modifier in option_rows:
        options[modifier["group_id"]].append(modifier)
    group_rows = {row["id"]: {**row, "modifiers": options[row["id"]]} for row in extras}
    variants = defaultdict(list)
    for row in active(m.variants, m.variants.c.item_id.in_(ids)):
        variants[row["item_id"]].append(row)
    assignments = defaultdict(list)
    mappings = db.execute(
        select(m.item_groups.c.item_id, m.item_groups.c.group_id).where(
            m.item_groups.c.tenant_id == tenant, m.item_groups.c.item_id.in_(ids)
        )
    )
    for item_id, group_id in mappings:
        if group_id in group_rows:
            assignments[item_id].append(group_rows[group_id])
    areas = active(m.preparation)
    area_ids = {area["id"] for area in areas}
    config = db.execute(
        select(m.settings.c.default_preparation_id, m.settings.c.preferences).where(
            m.settings.c.tenant_id == tenant
        )
    ).first()
    default, preferences = config if config else (None, {})
    for row in items:
        key = row["id"]
        row["variants"] = variants[key]
        row["modifier_groups"] = sorted(
            assignments[key], key=lambda entry: (entry["position"], entry["name"])
        )
        if row["preparation_id"] not in area_ids:
            row["preparation_id"] = default if default in area_ids else None
    return {
        "categories": categories,
        "items": items,
        "preparation_areas": areas,
        "preferences": {
            "currency": "GTQ",
            "timezone": preferences.get("timezone", "America/Guatemala"),
            "order_modes": preferences.get("order_modes", ["dine_in"]),
        },
        "payment_methods": [
            {"id": row["id"], "name": row["name"]} for row in active(m.payment_methods)
        ],
    }


def calculate(db, tenant, key, data):
    item = get_row(db, m.items, tenant, key)
    category = get_row(db, m.categories, tenant, item["category_id"])
    if not category["active"] or not item["active"] or not item["available"]:
        raise HTTPException(409, "El platillo no está disponible")
    unit = item["price_cents"]
    if data.variant_id:
        variant = get_row(db, m.variants, tenant, data.variant_id)
        if variant["item_id"] != key or not variant["active"] or not variant["available"]:
            raise HTTPException(422, "La variante no está disponible para este platillo")
        unit = (
            variant["price_cents"]
            if variant["pricing"] == "replace"
            else unit + variant["price_cents"]
        )
    selected = set(data.modifier_ids)
    if len(selected) != len(data.modifier_ids):
        raise HTTPException(422, "Cada extra se selecciona una vez por platillo")
    groups = (
        db.execute(
            scoped_rows(db, m.groups, tenant)
            .join(
                m.item_groups,
                (m.item_groups.c.tenant_id == m.groups.c.tenant_id)
                & (m.item_groups.c.group_id == m.groups.c.id),
            )
            .where(m.item_groups.c.item_id == key, m.groups.c.active)
        )
        .mappings()
        .all()
    )
    group_ids = {group["id"] for group in groups}
    included = (
        db.execute(
            scoped_rows(db, m.modifiers, tenant).where(
                m.modifiers.c.id.in_(selected),
                m.modifiers.c.group_id.in_(group_ids),
                m.modifiers.c.active,
            )
        )
        .mappings()
        .all()
    )
    if len(included) != len(selected):
        raise HTTPException(422, "Hay extras que no están disponibles para este platillo")
    counts = Counter(modifier["group_id"] for modifier in included)
    for group in groups:
        if not group["minimum"] <= counts[group["id"]] <= group["maximum"]:
            raise HTTPException(422, f"Verifica la selección del grupo {group['name']}")
    extras = sum(modifier["price_cents"] for modifier in included)
    unit += extras
    return {
        "item_id": key,
        "unit_cents": unit,
        "extras_cents": extras,
        "quantity": data.quantity,
        "total_cents": unit * data.quantity,
        "currency": "GTQ",
    }


def catalog_access(request, db, slug):
    _, access = restaurant_user(request, db, slug, None)
    if not {"pos.access", "menu.view"} & access.permissions:
        raise HTTPException(403, "Permiso de catálogo insuficiente")
    return access.tenant.id


@router.get("/catalog")
def operational_catalog(slug: str, request: Request, db: DB):
    return catalog(db, catalog_access(request, db, slug))


@router.post("/catalog/{key}/quote")
def quote(slug: str, key: str, data: Quote, request: Request, db: DB):
    return calculate(db, catalog_access(request, db, slug), key, data)


@router.get("/catalog/tables")
def operational_tables(slug: str, request: Request, db: DB):
    _, access = restaurant_user(request, db, slug, "tables.view")
    tenant = access.tenant.id
    rows = db.execute(
        scoped_rows(db, m.tables, tenant)
        .join(
            m.areas,
            (m.areas.c.id == m.tables.c.area_id) & (m.areas.c.tenant_id == m.tables.c.tenant_id),
        )
        .where(m.areas.c.active)
        .order_by(m.areas.c.position, m.tables.c.position, m.tables.c.number)
    )
    return [dict(row) for row in rows.mappings()]


@router.get("/customers/export")
def export_customers(slug: str, request: Request, db: DB):
    _, access = restaurant_user(request, db, slug, "customers.export")
    fields = ("name", "tax_id", "phone", "email", "address", "active")
    rows = db.execute(
        select(*(m.customers.c[field] for field in fields))
        .where(condition(m.customers, access.tenant.id))
        .order_by(m.customers.c.name)
    ).all()
    db.rollback()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(("Nombre", "NIT", "Teléfono", "Correo", "Dirección", "Activo"))
    writer.writerows([csv_cell(value) for value in row] for row in rows)
    return Response(
        output.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="clientes.csv"'},
    )
