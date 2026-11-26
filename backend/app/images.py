from base64 import b64decode
from binascii import Error
from io import BytesIO

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

MAX_BYTES = 2 * 1024 * 1024


def image_data(content: str):
    try:
        raw = b64decode(content, validate=True)
        if len(raw) > MAX_BYTES:
            raise ValueError
        with Image.open(BytesIO(raw), formats=["PNG", "JPEG", "WEBP", "ICO"]) as source:
            if max(source.size) > 2400 or getattr(source, "is_animated", False):
                raise ValueError
            pixels = source.convert("RGBA")
            result = BytesIO()
            pixels.save(result, format="PNG", optimize=True)
        data = result.getvalue()
        if len(data) > MAX_BYTES:
            raise ValueError
    except (
        Error,
        ValueError,
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
    ) as exc:
        raise HTTPException(422, "La imagen debe ser válida, de hasta 2400 px y 2 MB") from exc
    return data, "image/png"
