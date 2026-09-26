import os
import uuid

from app.core.config import settings

_cloudinary_configured = False


def _ensure_cloudinary_configured():
    global _cloudinary_configured
    if _cloudinary_configured:
        return
    import cloudinary

    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )
    _cloudinary_configured = True


def save_bytes(raw_bytes: bytes, filename: str, resource_type: str = "image") -> str:
    if settings.use_cloudinary:
        _ensure_cloudinary_configured()
        import cloudinary.uploader

        result = cloudinary.uploader.upload(
            raw_bytes,
            resource_type=resource_type,
            folder="smartclick",
            public_id=f"{os.path.splitext(filename)[0]}_{uuid.uuid4().hex[:8]}",
        )
        return result["secure_url"]

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    path = os.path.join(settings.UPLOAD_DIR, filename)
    with open(path, "wb") as f:
        f.write(raw_bytes)
    return f"/static/{filename}"


def delete_by_url(url: str) -> None:
    if not url.startswith("http") or not settings.use_cloudinary:
        return
    try:
        _ensure_cloudinary_configured()
        import cloudinary.uploader

        parts = url.split("/upload/")[-1]
        segments = parts.split("/")
        if segments and segments[0].startswith("v") and segments[0][1:].isdigit():
            segments = segments[1:]
        public_id = "/".join(segments)
        public_id = os.path.splitext(public_id)[0]
        cloudinary.uploader.destroy(public_id, resource_type="image")
    except Exception as e:
        print(f"[storage] Best-effort Cloudinary delete failed for {url}: {e}")