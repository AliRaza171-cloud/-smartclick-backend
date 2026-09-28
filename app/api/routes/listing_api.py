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
switches them on in Admin > Products. A category that doesn't exist yet is
created (LISTING_API_CREATE_CATEGORIES), so products land where they belong.

Keys: the fixed LISTING_API_KEY from .env, or a key issued by one-click connect:
    POST /listing-api/connect   (admin login) {state, callback_url}
The admin approves on the website's /listing-agent/connect page; this backend then
creates a key ("lak_<id>.<signature>", signed with LISTING_API_SIGNING_SECRET or the
JWT secret, so no database table is needed) and sends it to Listing Agent's callback.
Revoke one key by adding its <id> to LISTING_API_REVOKED; changing the signing secret
revokes them all. LISTING_API_CONNECT=false turns one-click connect off.
"""
import hashlib
import hmac
import json
import os
import secrets
import uuid
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.api.routes.categories import _slugify
from app.core.config import settings
from app.models.category import Category
from app.models.product import Product
from app.models.user import User, UserRole
from app.services import storage_service

ALLOWED_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def _signing_secret() -> bytes:
    return (settings.LISTING_API_SIGNING_SECRET or settings.JWT_SECRET_KEY).encode()


def _signature(key_id: str) -> str:
    return hmac.new(_signing_secret(), f"listing-api:{key_id}".encode(), hashlib.sha256).hexdigest()[:40]


def issue_key() -> str:
    key_id = secrets.token_hex(8)
    return f"lak_{key_id}.{_signature(key_id)}"


def _issued_key_ok(key: str) -> bool:
    if not settings.LISTING_API_CONNECT or not key.startswith("lak_") or "." not in key:
        return False
    key_id, sig = key[4:].split(".", 1)
    revoked = {k.strip() for k in settings.LISTING_API_REVOKED.split(",") if k.strip()}
    return key_id not in revoked and hmac.compare_digest(sig.encode(), _signature(key_id).encode())


def require_listing_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = settings.LISTING_API_KEY
    if not expected and not settings.LISTING_API_CONNECT:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The Listing API is turned off on this store.")
    if x_api_key and expected and hmac.compare_digest(x_api_key.encode(), expected.encode()):
        return
    if x_api_key and _issued_key_ok(x_api_key):
        return
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
    """-> (category name, matched). An existing category is matched by name (any case);
    a new name is created as a category (LISTING_API_CREATE_CATEGORIES). Only when no name
    is given (or creating is off) does it fall back to the first category, flagged for review."""
    name = " ".join(str(wanted or "").split())[:60]
    if name:
        match = db.query(Category).filter(func.lower(Category.name) == name.lower()).first()
        if match:
            return match.name, True
        if settings.LISTING_API_CREATE_CATEGORIES:
            slug, base, n = _slugify(name), _slugify(name), 2
            while db.query(Category).filter(Category.slug == slug).first():
                slug, n = f"{base}-{n}", n + 1
            last = db.query(func.max(Category.sort_order)).scalar() or 0
            db.add(Category(name=name, slug=slug, sort_order=last + 1))
            db.flush()
            return name, True
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


# ---------------------------------------------------------------- one-click connect

connect_router = APIRouter(prefix="/listing-api/connect", tags=["listing-api"])


class ConnectIn(BaseModel):
    state: str = Field(min_length=8, max_length=100)
    callback_url: str = Field(min_length=10, max_length=500)


@connect_router.post("")
async def approve_connection(data: ConnectIn, _admin=Depends(require_admin)):
    """An admin clicked Approve on /listing-agent/connect: create a key and hand it to Listing Agent.

    Normally this server posts the key to Listing Agent's callback. When Listing Agent runs on the
    admin's own PC (callback on localhost), a hosted server like Render can't reach it — so the key
    goes back to the admin's browser (they're a logged-in admin) with {"deliver": "browser"}, and
    the approval page submits it to the callback itself. Same if this server can't reach it at all."""
    if not settings.LISTING_API_CONNECT:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "One-click connect is turned off on this store.")
    target = urlsplit(data.callback_url)
    local = target.scheme == "http" and target.hostname in ("localhost", "127.0.0.1")
    if not target.hostname or not (target.scheme == "https" or local):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The connect link is invalid (callback must be https).")
    key = issue_key()
    payload = {"state": data.state, "api_key": key, "store_name": settings.STORE_NAME}
    browser = {"deliver": "browser", "callback_url": data.callback_url, **payload}
    if local:
        return browser
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(data.callback_url, json=payload)
    except httpx.HTTPError:
        return browser
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail") or r.text[:200]
        except ValueError:
            detail = r.text[:200]
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Listing Agent didn't accept the connection: {detail}")
    return {"ok": True}
