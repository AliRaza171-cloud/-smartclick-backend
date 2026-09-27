"""
Listing API — lets Listing Agent (the AI listing tool) publish products into
this store. It's a small machine-to-machine API, separate from the admin
routes: it authenticates with one secret key (LISTING_API_KEY in .env) sent
as the X-Api-Key header, instead of an admin login.

    GET  /listing-api/ping                 -> {"store_name", "max_images"}   (connection test)
    GET  /listing-api/categories           -> [{"id", "name"}]                (so the AI picks a real one)
    POST /listing-api/products             multipart: data=<JSON>, images=<files>  -> {"id", "url", "status"}
    PUT  /listing-api/products/{id}        same body; replaces the product's content (re-publish)

Products created here are marked ai_generated. "draft" mode creates them with
is_active = false, so they stay hidden from the storefront until an admin
switches them on in Admin > Products.

Leave LISTING_API_KEY empty to switch the whole API off.
"""
import hmac
import json
import os
import uuid
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.models.category import Category
from app.models.product import Product
from app.models.user import User, UserRole
from app.services import storage_service

ALLOWED_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def require_listing_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = settings.LISTING_API_KEY
    if not expected:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The Listing API is turned off on this store.")
    if not x_api_key or not hmac.compare_digest(x_api_key.encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key.")


router = APIRouter(prefix="/listing-api", tags=["listing-api"], dependencies=[Depends(require_listing_key)])


def _product_url(product_id) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/product/{product_id}"


def _owner(db: Session) -> User:
    """Products need a creator; Listing API products belong to the first admin."""
    admin = db.query(User).filter(User.role == UserRole.admin).order_by(User.created_at).first()
    if not admin:
        raise HTTPException(status.HTTP_409_CONFLICT, "This store has no admin account yet — create one first.")
    return admin


def _category(db: Session, wanted: str | None) -> tuple[str, bool]:
    """-> (category name, matched). Unknown or missing names fall back to the first
    category and the product is flagged for review, so a publish never fails on this."""
    if wanted:
        match = db.query(Category).filter(Category.name.ilike(wanted.strip())).first()
        if match:
            return match.name, True
    first = db.query(Category).order_by(Category.sort_order, Category.name).first()
    if not first:
        raise HTTPException(status.HTTP_409_CONFLICT, "This store has no categories yet — add one in Admin > Categories.")
    return first.name, False


def _parse(data: str) -> dict:
    try:
        body = json.loads(data)
        if not isinstance(body, dict):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "data must be a JSON object.")

    title = str(body.get("title") or "").strip()
    description = str(body.get("description") or "").strip()
    if not title or not description:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "title and description are required.")
    try:
        price = Decimal(str(body.get("price")))
    except (InvalidOperation, TypeError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "price must be a number.")
    if price <= 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "price must be greater than 0.")
    discount = body.get("discount_pct")
    if discount is not None:
        try:
            discount = int(discount)
        except (TypeError, ValueError):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "discount_pct must be a whole number.")
        if not 0 < discount <= 100:
            discount = None
    highlights = [str(h).strip() for h in (body.get("highlights") or []) if str(h).strip()]
    if highlights:
        # The storefront shows the description as one paragraph, so highlights go in as "•" points.
        description = description + "\n\n" + "\n".join(f"• {h}" for h in highlights)
    tags = [str(t).strip()[:60] for t in (body.get("tags") or []) if str(t).strip()][:20]
    return {
        "title": title[:200],
        "description": description,
        "price": price,
        "discount_pct": discount,
        "free_shipping": bool(body.get("free_shipping")),
        "tags": tags,
        "category": body.get("category"),
        "is_active": body.get("mode") == "live",
    }


async def _save_images(images: list[UploadFile]) -> list[str]:
    if not images:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "At least one image is required.")
    urls = []
    for image in images[: settings.MAX_PRODUCT_IMAGES]:  # extra photos are skipped, not an error
        ext = ALLOWED_IMAGE_TYPES.get((image.content_type or "").split(";")[0])
        if not ext:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unsupported image type: {image.content_type}.")
        raw = await image.read()
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Each image must be between 1 byte and 8 MB.")
        urls.append(storage_service.save_bytes(raw, f"{uuid.uuid4().hex}{ext}", resource_type="image"))
    return urls


@router.get("/ping")
def ping():
    return {"store_name": settings.STORE_NAME, "max_images": settings.MAX_PRODUCT_IMAGES}


@router.get("/categories")
def categories(db: Session = Depends(get_db)):
    rows = db.query(Category).order_by(Category.sort_order, Category.name).all()
    return [{"id": str(c.id), "name": c.name} for c in rows]


@router.post("/products", status_code=status.HTTP_201_CREATED)
async def create_product(
    data: str = Form(...),
    images: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    fields = _parse(data)
    category, matched = _category(db, fields.pop("category"))
    owner = _owner(db)
    image_urls = await _save_images(images)
    product = Product(
        **fields,
        category=category,
        image_urls=image_urls,
        ai_generated=True,
        ai_flagged_needs_review=not matched,
        created_by=owner.id,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return {"id": str(product.id), "url": _product_url(product.id),
            "status": "live" if product.is_active else "draft", "category": category}


@router.put("/products/{product_id}")
async def update_product(
    product_id: str,
    data: str = Form(...),
    images: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    try:
        uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found.")
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found.")

    fields = _parse(data)
    category, matched = _category(db, fields.pop("category"))
    new_images = await _save_images(images)
    old_images = list(product.image_urls or [])

    for key, value in fields.items():
        setattr(product, key, value)
    product.category = category
    product.image_urls = new_images
    product.ai_generated = True
    product.ai_flagged_needs_review = not matched
    db.commit()
    db.refresh(product)

    for url in old_images:  # best effort; only removes Cloudinary copies
        storage_service.delete_by_url(url)
    return {"id": str(product.id), "url": _product_url(product.id),
            "status": "live" if product.is_active else "draft", "category": category}