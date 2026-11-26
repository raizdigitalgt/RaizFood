from base64 import b64encode
from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import restaurant_models as models
from tests.conftest import NORTH, SOUTH


def create(client, resource, body, base=NORTH):
    response = client.post(f"{base}/records/{resource}", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def replace(client, resource, key, body, base=NORTH):
    return client.put(f"{base}/records/{resource}/{key}", json=body)


def image_encoded(format_name="PNG"):
    image = Image.new("RGBA", (28, 20), (245, 155, 30, 100))
    buffer = BytesIO()
    image.save(buffer, format_name)
    return b64encode(buffer.getvalue()).decode()


def upload(client, folder=None, base=NORTH, format_name="PNG"):
    response = client.post(
        f"{base}/media/files",
        json={
            "name": "Plato de demostración",
            "folder_id": folder,
            "content": image_encoded(format_name),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_menu_catalog_price_history_and_variants(tenants):
    _, _, client, _ = tenants
    category = create(client, "categories", {"name": "Tacos", "position": 4})
    assert client.post(f"{NORTH}/records/categories", json={"name": "  TACOS "}).status_code == 409
    assert (
        replace(
            client, "categories", category["id"], {"name": "Tacos de la casa", "position": 1}
        ).status_code
        == 200
    )
    area = create(client, "preparation", {"name": "Cocina"})
    group = create(client, "groups", {"name": "Extras", "minimum": 1, "maximum": 2})
    assert (
        client.post(
            f"{NORTH}/records/groups",
            json={
                "name": "Inválido",
                "minimum": 2,
                "maximum": 1,
            },
        ).status_code
        == 422
    )
    extra = create(
        client, "modifiers", {"name": "Queso", "group_id": group["id"], "price_cents": 300}
    )
    other = create(client, "groups", {"name": "Aderezos"})
    foreign_extra = create(client, "modifiers", {"name": "Salsa", "group_id": other["id"]})
    image = upload(client)
    fields = {
        "name": "Taco",
        "code": "TC01",
        "category_id": category["id"],
        "price_cents": 1500,
        "preparation_id": area["id"],
        "image_id": image["id"],
        "group_ids": [group["id"]],
    }
    assert (
        client.post(f"{NORTH}/records/items", json={**fields, "price_cents": -1}).status_code == 422
    )
    assert (
        client.post(f"{NORTH}/records/items", json={**fields, "tenant_id": "otro"}).status_code
        == 422
    )
    item = create(client, "items", fields)
    assert client.post(f"{NORTH}/records/items", json={**fields, "code": "tc01"}).status_code == 409
    variance = {
        "item_id": item["id"],
        "name": "Grande",
        "code": "TC01-G",
        "pricing": "adjust",
        "price_cents": 500,
    }
    variant = create(client, "variants", variance)
    assert (
        client.post(
            f"{NORTH}/records/variants", json={**variance, "code": "bad", "price_cents": -2000}
        ).status_code
        == 422
    )
    regular = create(
        client,
        "variants",
        {
            **variance,
            "name": "Precio fijo",
            "code": "TC-R",
            "pricing": "replace",
            "price_cents": 1800,
        },
    )
    quote = f"{NORTH}/catalog/{item['id']}/quote"
    assert client.post(quote, json={}).status_code == 422
    for ids in ([extra["id"], extra["id"]], [foreign_extra["id"]]):
        assert client.post(quote, json={"modifier_ids": ids}).status_code == 422
    assert (
        client.post(
            quote, json={"variant_id": regular["id"], "modifier_ids": [extra["id"]]}
        ).json()["total_cents"]
        == 2100
    )
    assert (
        client.post(
            quote, json={"variant_id": variant["id"], "modifier_ids": [extra["id"]], "quantity": 2}
        ).json()["total_cents"]
        == 4600
    )
    assert replace(client, "items", item["id"], {**fields, "price_cents": 1600}).status_code == 200
    prices = client.get(f"{NORTH}/items/{item['id']}/prices").json()
    assert {row["price_cents"] for row in prices} == {1500, 1600, 1800, 500}
    result = client.get(f"{NORTH}/catalog").json()
    (dish,) = result["items"]
    assert dish["image_id"] == image["id"] and dish["preparation_id"] == area["id"]
    assert dish["modifier_groups"][0]["modifiers"][0]["name"] == "Queso"
    assert len(dish["variants"]) == 2
    duplicated = client.post(
        f"{NORTH}/items/{item['id']}/duplicate", json={"name": "Otro taco", "code": "COPY"}
    )
    assert duplicated.status_code == 201, duplicated.text
    assert (
        client.post(
            f"{NORTH}/items/{item['id']}/duplicate", json={"name": "Otro", "code": "COPY"}
        ).status_code
        == 409
    )
    assert replace(client, "items", item["id"], {**fields, "available": False}).status_code == 200
    assert client.post(quote, json={"modifier_ids": [extra["id"]]}).status_code == 409
    assert (
        client.get(f"{NORTH}/records/items", params={"available": "false", "q": "TC01"}).json()[
            "total"
        ]
        == 1
    )
    assert client.get(f"{NORTH}/records/items", params={"active": "maybe"}).status_code == 422
    assert client.get(f"{NORTH}/records/categories").json()["items"][0]["associated"] == 2
    assert client.delete(f"{NORTH}/records/categories/{category['id']}").status_code == 204
    assert client.get(f"{NORTH}/catalog").json()["items"] == []


def test_media_settings_tables_and_customers(tenants):
    app, _, client, _ = tenants
    root = create(client, "folders", {"name": "Fotos"})
    child = create(client, "folders", {"name": "Comidas", "parent_id": root["id"]})
    assert (
        replace(
            client, "folders", root["id"], {"name": "Fotos", "parent_id": child["id"]}
        ).status_code
        == 409
    )
    assert client.delete(f"{NORTH}/records/folders/{root['id']}").status_code == 409
    assert (
        client.post(
            f"{NORTH}/media/files", json={"name": "Inválida", "content": "ZGF0b3M="}
        ).status_code
        == 422
    )
    image = upload(client, child["id"])
    assert upload(client, child["id"], format_name="AVIF")["width"] == 28
    assert image["width"] == 28 and image["height"] == 20
    asset = client.get(f"{NORTH}/media/files/{image['id']}/content", params={"thumb": True})
    assert asset.status_code == 200 and asset.headers["Content-Type"] == "image/webp"
    with Image.open(BytesIO(asset.content)) as decoded:
        assert decoded.getpixel((0, 0))[3] == 100
    app.state.settings.restaurant_image_max_bytes = 1024
    try:
        assert (
            client.post(
                f"{NORTH}/media/files",
                json={"name": "Límite", "content": b64encode(bytes(1200)).decode()},
            ).status_code
            == 413
        )
        assert client.get(f"{NORTH}/media/limits").json()["max_bytes"] == 1024
    finally:
        app.state.settings.restaurant_image_max_bytes = 8_388_608
    assert (
        replace(client, "files", image["id"], {"name": "Portada", "folder_id": None}).status_code
        == 200
    )
    assert (
        client.get(f"{NORTH}/records/files", params={"folder_id": "root", "q": "Portada"}).json()[
            "total"
        ]
        == 1
    )
    area = create(client, "areas", {"name": "Salón"})
    spare = create(client, "areas", {"name": "Terraza"})
    kitchen = create(client, "preparation", {"name": "Barra"})
    assert (
        client.put(
            f"{NORTH}/settings",
            json={
                "name": "Restaurante editado",
                "timezone": "America/Guatemala",
                "logo_id": image["id"],
                "default_area_id": area["id"],
                "default_preparation_id": kitchen["id"],
                "default_available": False,
                "display_name": "Portal norte",
                "department": "Guatemala",
                "municipality": "Mixco",
                "days": ["lun", "mar", "lun"],
                "order_modes": ["dine_in", "delivery"],
                "accent": "#a23111",
            },
        ).status_code
        == 200
    )
    assert client.get(f"{NORTH}/settings").json()["days"] == ["lun", "mar"]
    assert client.get(f"{NORTH}/appearance").json()["display_name"] == "Portal norte"
    defaults = client.get(f"{NORTH}/editor-defaults").json()
    assert defaults["default_available"] is False and defaults["default_area_id"] == area["id"]
    cat = create(client, "categories", {"name": "Especiales"})
    pending = create(
        client,
        "items",
        {"name": "Platillo nuevo", "code": "P-001", "category_id": cat["id"], "price_cents": 1400},
    )
    assert pending["available"] is False
    prepared = client.get(f"{NORTH}/catalog").json()
    assert prepared["items"][0]["preparation_id"] == kitchen["id"]
    assert prepared["preferences"]["order_modes"] == ["dine_in", "delivery"]
    assert client.delete(f"{NORTH}/records/files/{image['id']}").status_code == 409
    assert (
        client.put(f"{NORTH}/settings", json={"name": "Norte", "accent": "rojo"}).status_code == 422
    )
    assert (
        client.post(
            f"{NORTH}/tables/batch",
            json={"area_id": area["id"], "prefix": "Mesa", "quantity": 3, "capacity": 4},
        ).json()["count"]
        == 3
    )
    assert (
        client.post(
            f"{NORTH}/tables/batch",
            json={"area_id": area["id"], "prefix": "mesa", "quantity": 5, "capacity": 4},
        ).status_code
        == 409
    )
    assert (
        client.get(f"{NORTH}/records/tables", params={"area_id": area["id"]}).json()["total"] == 3
    )
    single = create(client, "tables", {"area_id": spare["id"], "number": "Mesa 01"})
    assert (
        replace(
            client,
            "tables",
            single["id"],
            {"area_id": spare["id"], "number": "Mesa 01", "state": "cleaning"},
        ).json()["state"]
        == "cleaning"
    )
    assert (
        client.post(
            f"{NORTH}/records/tables",
            json={"area_id": spare["id"], "number": "2", "state": "occupied"},
        ).status_code
        == 422
    )
    assert client.delete(f"{NORTH}/records/areas/{spare['id']}").status_code == 204
    assert len(client.get(f"{NORTH}/catalog/tables").json()) == 3
    assert client.delete(f"{NORTH}/records/tables/{single['id']}").status_code == 204
    customer = create(
        client,
        "customers",
        {
            "name": "=Cliente de prueba",
            "tax_id": "CF",
            "email": "cliente@example.org",
            "phone": "1234",
        },
    )
    assert (
        client.get(f"{NORTH}/records/customers", params={"q": "cliente@example.org"}).json()[
            "total"
        ]
        == 1
    )
    assert (
        replace(
            client, "customers", customer["id"], {"name": "=Cliente de prueba", "active": False}
        ).status_code
        == 200
    )
    assert "'=Cliente de prueba" in client.get(f"{NORTH}/customers/export").text
    assert create(client, "payment-methods", {"name": "Transferencia"})["name"] == "Transferencia"
    overview = client.get(f"{NORTH}/overview").json()
    assert overview["counts"]["tables"] == 3 and overview["counts"]["customers"] == 1
    assert client.get(f"{NORTH}/audit", params={"q": "settings.logo"}).json()["total"] == 1


def test_tenant_isolation_for_all_restaurant_records(tenants):
    app, _, north, south = tenants
    cat = create(north, "categories", {"name": "Única"})
    assert create(south, "categories", {"name": "Única"}, SOUTH)["id"] != cat["id"]
    station = create(north, "preparation", {"name": "Cocina"})
    image = upload(north)
    area = create(north, "areas", {"name": "Comedor"})
    table = create(north, "tables", {"area_id": area["id"], "number": "1"})
    group = create(north, "groups", {"name": "Aderezos"})
    extra = create(north, "modifiers", {"group_id": group["id"], "name": "Chile"})
    item = create(
        north,
        "items",
        {
            "category_id": cat["id"],
            "name": "Producto",
            "code": "FOOD",
            "price_cents": 2000,
            "group_ids": [group["id"]],
        },
    )
    variant = create(
        north,
        "variants",
        {"item_id": item["id"], "name": "Grande", "code": "FOOD-G", "price_cents": 2500},
    )
    customer = create(north, "customers", {"name": "Cliente privado"})
    folder = create(north, "folders", {"name": "Privada"})
    for key, row in (
        ("categories", cat),
        ("preparation", station),
        ("files", image),
        ("areas", area),
        ("tables", table),
        ("groups", group),
        ("modifiers", extra),
        ("items", item),
        ("variants", variant),
        ("customers", customer),
        ("folders", folder),
    ):
        assert south.get(f"{SOUTH}/records/{key}/{row['id']}").status_code == 404
        assert south.delete(f"{SOUTH}/records/{key}/{row['id']}").status_code == 404
    assert south.get(f"{NORTH}/settings").status_code == 404
    assert south.get(f"{NORTH}/catalog").status_code == 404
    assert south.get(f"{SOUTH}/media/files/{image['id']}/content").status_code == 404
    assert (
        south.put(f"{SOUTH}/settings", json={"name": "Sur", "logo_id": image["id"]}).status_code
        == 404
    )
    assert (
        south.post(
            f"{SOUTH}/records/items",
            json={"name": "Erróneo", "code": "1", "price_cents": 0, "category_id": cat["id"]},
        ).status_code
        == 404
    )
    assert south.get(f"{SOUTH}/audit", params={"q": table["id"]}).json()["total"] == 0
    with Session(app.state.engine) as db, pytest.raises(IntegrityError):
        scope = (
            db.execute(models.categories.select().where(models.categories.c.id == cat["id"]))
            .mappings()
            .one()["tenant_id"]
        )
        area_s = create(south, "areas", {"name": "Sur"}, SOUTH)
        db.execute(
            insert(models.tables).values(
                tenant_id=scope,
                area_id=area_s["id"],
                number="Cruce",
                normalized_number="cruce",
                capacity=4,
                state="available",
            )
        )
