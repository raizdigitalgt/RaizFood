from PIL import Image, ImageDraw
from sqlalchemy import insert, select

from app import restaurant_models as m
from app.models import Membership, Role, User
from app.restaurant_media import encode
from app.restaurant_records import condition, get_row, normalized, record, resource_for
from app.restaurant_schemas import MenuItem


def existing(db, table, tenant, *filters):
    return db.scalar(select(table.c.id).where(condition(table, tenant), *filters).limit(1))


def seed_restaurant(db, tenant, code):
    actor = db.scalar(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .join(Role, (Role.tenant_id == Membership.tenant_id) & (Role.id == Membership.role_id))
        .where(Membership.tenant_id == tenant.id, Role.code == "admin")
        .limit(1)
    )
    if not actor:
        return
    key = tenant.id

    def put(resource, criteria, data):
        table = resource_for(resource).table
        found = existing(db, table, key, *criteria)
        return get_row(db, table, key, found) if found else record(db, resource, key, actor, data)

    def named(title, **kwargs):
        return {
            "name": title,
            "description": "Datos de demostración",
            "position": 0,
            "active": True,
            **kwargs,
        }

    def title(resource, name, **kwargs):
        table = resource_for(resource).table
        return put(resource, (table.c.normalized_name == normalized(name),), named(name, **kwargs))[
            "id"
        ]

    restaurant_area = title("areas", "Salón principal")
    kitchen = title("preparation", "Cocina")
    bar = title("preparation", "Barra")
    food_category = title("categories", "Tacos y antojitos" if code == "basic" else "Hamburguesas")
    drink_category = title("categories", "Bebidas", position=2)
    group = title("groups", "Ingredientes adicionales", minimum=0, maximum=2)
    for name, price in (("Extra queso", 500), ("Extra aguacate", 400)):
        put(
            "modifiers",
            (m.modifiers.c.group_id == group, m.modifiers.c.normalized_name == normalized(name)),
            named(name, group_id=group, price_cents=price),
        )

    folder = put(
        "folders",
        (
            m.media_folders.c.parent_id.is_(None),
            m.media_folders.c.normalized_name == "demostración",
        ),
        {"name": "Demostración", "parent_id": None},
    )["id"]
    meals = (
        ["Tacos de res", "Tacos de pollo", "Quesadillas", "Burritos"]
        if code == "basic"
        else ["Hamburguesa clásica", "Hamburguesa doble", "Hamburguesa con queso", "Papas fritas"]
    )
    palette = ("#9a431b", "#845c24", "#486052", "#804b57", "#294c66")
    for index, (name, tint) in enumerate(
        zip([*meals, "Bebida de la casa"], palette, strict=True), 1
    ):
        filename = f"demo-{index}.webp"
        photo = existing(
            db,
            m.media_files,
            key,
            m.media_files.c.folder_id == folder,
            m.media_files.c.name == filename,
        )
        if not photo:
            image = Image.new("RGB", (480, 300), "#182232")
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((42, 46, 438, 254), radius=38, fill=tint)
            draw.ellipse((166, 76, 314, 224), outline="#f1efdb", width=8)
            draw.arc((188, 105, 292, 196), 20, 340, fill="#f4ba7b", width=9)
            main, thumb = encode(image, 480, 85), encode(image, 320, 78)
            photo = db.execute(
                insert(m.media_files).values(
                    tenant_id=key,
                    folder_id=folder,
                    name=filename,
                    width=480,
                    height=300,
                    size=len(main),
                    content=main,
                    thumbnail=thumb,
                )
            ).inserted_primary_key[0]
        item_code = f"DEMO-{index}"
        data = MenuItem(
            name=name,
            code=item_code,
            price_cents=1200 + 400 * index,
            category_id=drink_category if index == 5 else food_category,
            preparation_id=bar if index == 5 else kitchen,
            image_id=photo,
            group_ids=[] if index == 5 else [group],
            position=index,
            description="Platillo de muestra",
        ).model_dump()
        item = put("items", (m.items.c.normalized_code == normalized(item_code),), data)
        if index in {1, 5}:
            variant = f"{item_code}-G"
            put(
                "variants",
                (m.variants.c.normalized_code == normalized(variant),),
                named(
                    "Grande",
                    item_id=item["id"],
                    code=variant,
                    price_cents=500,
                    pricing="adjust",
                    available=True,
                    image_id=None,
                ),
            )
    for index in range(1, 5):
        number = f"Mesa {index:02d}"
        put(
            "tables",
            (
                m.tables.c.area_id == restaurant_area,
                m.tables.c.normalized_number == normalized(number),
            ),
            {
                "number": number,
                "name": "",
                "area_id": restaurant_area,
                "capacity": 4,
                "state": "available",
                "position": index,
            },
        )
    put(
        "customers",
        (m.customers.c.email == f"cliente@{tenant.slug}.example.org",),
        {
            "name": "Cliente de demostración",
            "email": f"cliente@{tenant.slug}.example.org",
            "tax_id": "",
            "phone": "",
            "address": "",
            "notes": "Perfil ficticio",
            "active": True,
        },
    )
