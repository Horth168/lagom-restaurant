"""Product photo storage: Cloudflare R2 when configured, otherwise the server's disk.

Every upload is opened and re-saved as a new JPEG by Pillow. This rejects files
that are not really images, removes hidden data (EXIF, GPS location) and limits
the size so menus load fast on phones.
"""
import io
import secrets
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import get_settings

MAX_BYTES = 8 * 1024 * 1024
MAX_SIDE = 1600
LOCAL_DIR = Path(__file__).resolve().parents[2] / "uploads"


class UploadProblem(ValueError):
    pass


def _clean_jpeg(data: bytes) -> bytes:
    if len(data) > MAX_BYTES:
        raise UploadProblem("Photo is too large (8 MB maximum).")
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()  # detects broken or fake image files
        img = Image.open(io.BytesIO(data))
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise UploadProblem("This file is not a photo (use JPG, PNG or WebP).")
    if img.format not in ("JPEG", "PNG", "WEBP"):
        raise UploadProblem("Use a JPG, PNG or WebP photo.")
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=84, optimize=True, progressive=True)  # saved without EXIF
    return out.getvalue()


def save_product_photo(data: bytes) -> str:
    """Returns the public URL of the stored photo."""
    jpeg = _clean_jpeg(data)
    name = f"products/{secrets.token_hex(12)}.jpg"
    s = get_settings()
    if s.r2_bucket and s.r2_access_key_id and s.r2_secret_access_key and s.r2_account_id:
        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=f"https://{s.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=s.r2_access_key_id,
            aws_secret_access_key=s.r2_secret_access_key,
            region_name="auto",
        )
        client.put_object(Bucket=s.r2_bucket, Key=name, Body=jpeg, ContentType="image/jpeg",
                          CacheControl="public, max-age=31536000, immutable")
        return f"{s.r2_public_base_url.rstrip('/')}/{name}"
    path = LOCAL_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(jpeg)
    return f"{s.backend_url.rstrip('/')}/uploads/{name}"
