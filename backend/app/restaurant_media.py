from base64 import b64decode
from io import BytesIO

from fastapi import APIRouter, HTTPException, Request, Response
from PIL import Image, ImageOps
from sqlalchemy import insert, or_, select

from app import restaurant_models as m
from app.access import audit
from app.auth import DB
from app.db import write_transaction
from app.operations import restaurant_user
from app.restaurant_records import condition, get_row
from app.restaurant_schemas import FileUpload

router = APIRouter(prefix="/restaurants/{slug}", tags=["Biblioteca del restaurante"])


def encode(source, size, quality):
    picture = source.copy()
    picture.thumbnail((size, size), Image.Resampling.LANCZOS)
    output = BytesIO()
    picture.save(output, "WEBP", quality=quality, method=4)
    return output.getvalue()


def images(value, limit):
    if len(value) > 4 * ((limit + 2) // 3):
        raise HTTPException(413, "La imagen supera el tamaño permitido")
    try:
        content = b64decode(value, validate=True)
        if len(content) > limit:
            raise HTTPException(413, "La imagen supera el tamaño permitido")
        with Image.open(BytesIO(content), formats=["PNG", "JPEG", "WEBP", "AVIF"]) as picture:
            if picture.width * picture.height > 32_000_000 or getattr(
                picture, "is_animated", False
            ):
                raise ValueError("Dimensiones de imagen inválidas")
            optimized = ImageOps.exif_transpose(picture).convert("RGBA")
            main = encode(optimized, 1800, 85)
            thumb = encode(optimized, 320, 78)
            return main, thumb, optimized.width, optimized.height
    except (ValueError, OSError, Image.DecompressionBombError) as error:
        raise HTTPException(422, "Sube una imagen válida JPG, PNG, WebP o AVIF") from error


@router.get("/media/limits")
def limits(slug: str, request: Request, db: DB):
    restaurant_user(request, db, slug, "media.manage")
    return {"max_bytes": request.app.state.settings.restaurant_image_max_bytes}


@router.post("/media/files", status_code=201)
def upload(slug: str, data: FileUpload, request: Request, db: DB):
    restaurant_user(request, db, slug, "media.manage")
    db.rollback()
    main, thumb, width, height = images(
        data.content, request.app.state.settings.restaurant_image_max_bytes
    )
    with write_transaction(db):
        actor, access = restaurant_user(request, db, slug, "media.manage")
        tenant = access.tenant.id
        if data.folder_id:
            get_row(db, m.media_folders, tenant, data.folder_id)
        key = db.execute(
            insert(m.media_files).values(
                tenant_id=tenant,
                name=data.name,
                folder_id=data.folder_id,
                width=width,
                height=height,
                size=len(main),
                content=main,
                thumbnail=thumb,
            )
        ).inserted_primary_key[0]
        audit(db, actor, "restaurant.files.upload", key, tenant)
        return get_row(db, m.media_files, tenant, key)


@router.get("/media/files/{key}/content")
def image_content(slug: str, key: str, request: Request, db: DB, thumb: bool = False):
    _, access = restaurant_user(request, db, slug, None)
    tenant = access.tenant.id
    scopes = access.permissions
    if "media.manage" not in scopes:
        where = select(m.settings.c.tenant_id).where(
            m.settings.c.tenant_id == tenant,
            or_(m.settings.c.logo_id == key, m.settings.c.cover_id == key),
        )
        brand = "dashboard.view" in scopes and db.scalar(where)
        catalog = bool({"menu.view", "pos.access"} & scopes) and any(
            db.scalar(
                select(table.c.id)
                .where(condition(table, tenant), table.c.image_id == key, table.c.active)
                .limit(1)
            )
            for table in (m.items, m.categories, m.variants)
        )
        if not brand and not catalog:
            raise HTTPException(404, "Imagen no disponible")
    block = m.media_files.c.thumbnail if thumb else m.media_files.c.content
    content = db.scalar(select(block).where(condition(m.media_files, tenant, key)))
    if content is None:
        raise HTTPException(404, "Imagen no disponible")
    return Response(content, media_type="image/webp")
