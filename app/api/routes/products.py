import os
import uuid
import json
from datetime import datetime, timedelta
from collections import Counter

import httpx
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, Depends
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.api.deps import require_admin, get_db
from app.models.user import User
from app.models.product import Product, Voucher
from app.models.category import Category
from app.models.order import Order, OrderStatus
from app.models.review import Review
from app.models.analytics import AnalyticsEvent
from app.services import storage_service
from app.schemas.product import ProductCreate, ProductOut, ProductUpdate

router = APIRouter(prefix="/products", tags=["products"])

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


@router.post("/analyze")
async def analyze_product(
    images: list[UploadFile] = File(...),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    files = [
        ("images", (image.filename, await image.read(), image.content_type))
        for image in images
    ]
    category_names = [c.name for c in db.query(Category).all()]

    try:
        async with httpx.AsyncClient(timeout=settings.AI_SERVICE_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{settings.AI_SERVICE_URL}/analyze",
                files=files,
                data={"categories": json.dumps(category_names)},
                headers={"X-Internal-Api-Key": settings.INTERNAL_AI_SERVICE_KEY},
            )
    except httpx.RequestError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The AI listing assistant is unavailable right now. You can still create "
            "the listing manually — category, title, and description are yours to fill in.",
        )

    if response.status_code != 200:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The AI listing assistant couldn't analyze these images. You can still create "
            "the listing manually.",
        )

    return response.json()


def _save_images(images: list[UploadFile]) -> list[str]:
    if not images:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "At least one image is required.")
    if len(images) > settings.MAX_PRODUCT_IMAGES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Too many images — max {settings.MAX_PRODUCT_IMAGES}."
        )

    urls = []
    for image in images:
        if image.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Unsupported file type: {image.content_type}. Use JPEG, PNG, or WebP.",
            )
        raw_bytes = image.file.read()
        ext = os.path.splitext(image.filename or "")[1] or ".jpg"
        filename = f"{uuid.uuid4().hex}{ext}"
        urls.append(storage_service.save_bytes(raw_bytes, filename, resource_type="image"))
    return urls

ALLOWED_VIDEO_CONTENT_TYPES = {"video/mp4", "video/webm", "video/quicktime"}


def _save_video(video: UploadFile | None) -> str | None:
    if video is None or not video.filename:
        return None
    if video.content_type not in ALLOWED_VIDEO_CONTENT_TYPES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unsupported video type: {video.content_type}. Use MP4, WebM, or MOV.",
        )
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    raw_bytes = video.file.read()
    ext = os.path.splitext(video.filename or "")[1] or ".mp4"
    filename = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(settings.UPLOAD_DIR, filename)
    with open(path, "wb") as f:
        f.write(raw_bytes)
    return f"/static/{filename}"


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    images: list[UploadFile] = File(...),
    video: UploadFile | None = File(None),
    title: str = Form(...),
    description: str = Form(...),
    category: str = Form(...),
    price: float = Form(...),
    discount_pct: int | None = Form(None),
    free_shipping: bool = Form(False),
    voucher_code: str | None = Form(None),
    tags: str = Form("[]"),
    ai_generated: bool = Form(False),
    ai_flagged_needs_review: bool = Form(False),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        tags_list = json.loads(tags)
        if not isinstance(tags_list, list):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "tags must be a JSON array of strings.")

    if not db.query(Category).filter(Category.name == category).first():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Category '{category}' doesn't exist yet — create it first via POST /categories.",
        )

    if voucher_code:
        voucher = db.query(Voucher).filter(Voucher.code == voucher_code.upper()).first()
        if not voucher:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"No voucher with code {voucher_code}.")
        voucher_code = voucher.code

    image_urls = _save_images(images)
    video_url = _save_video(video)

    data = ProductCreate(
        title=title,
        description=description,
        category=category,
        price=price,
        discount_pct=discount_pct,
        free_shipping=free_shipping,
        voucher_code=voucher_code,
        image_urls=image_urls,
        video_url=video_url,
        tags=tags_list,
        ai_generated=ai_generated,
        ai_flagged_needs_review=ai_flagged_needs_review,
    )

    product = Product(**data.model_dump(), created_by=admin.id)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.patch("/{product_id}/video", response_model=ProductOut)
async def update_product_video(
    product_id: str,
    video: UploadFile = File(...),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found.")
    product.video_url = _save_video(video)
    db.commit()
    db.refresh(product)
    return product


@router.get("", response_model=list[ProductOut])
def list_products(category: str | None = None, search: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Product).filter(Product.is_active == True)  # noqa: E712
    if category:
        query = query.filter(Product.category == category)
    if search:
        like = f"%{search}%"
        query = query.filter(or_(Product.title.ilike(like), Product.description.ilike(like)))
    products = query.order_by(Product.created_at.desc()).all()
    _attach_rating_aggregates(products, db)
    return products


def _attach_rating_aggregates(products: list[Product], db: Session) -> None:
    if not products:
        return
    ids = [p.id for p in products]
    rows = (
        db.query(Review.product_id, func.avg(Review.rating), func.count(Review.id))
        .filter(Review.product_id.in_(ids))
        .group_by(Review.product_id)
        .all()
    )
    stats = {pid: (round(float(avg), 1), count) for pid, avg, count in rows}
    for p in products:
        avg, count = stats.get(p.id, (None, 0))
        p.average_rating = avg
        p.review_count = count


@router.get("/badges")
def get_product_badges(db: Session = Depends(get_db)):
    active_ids = {str(pid) for (pid,) in db.query(Product.id).filter(Product.is_active == True)}  # noqa: E712
    badges: dict[str, str] = {}

    order_counts: Counter[str] = Counter()
    for (items,) in db.query(Order.items).filter(Order.status == OrderStatus.paid):
        for item in items or []:
            pid = item.get("product_id")
            if pid:
                order_counts[pid] += item.get("quantity", 1)
    for pid, _ in order_counts.most_common(5):
        if pid in active_ids:
            badges[pid] = "Best Seller"

    week_ago = datetime.utcnow() - timedelta(days=7)
    trending_rows = (
        db.query(AnalyticsEvent.product_id, func.count(AnalyticsEvent.id).label("views"))
        .filter(AnalyticsEvent.event_type == "product_view", AnalyticsEvent.created_at >= week_ago)
        .group_by(AnalyticsEvent.product_id)
        .order_by(func.count(AnalyticsEvent.id).desc())
        .limit(5)
        .all()
    )
    for pid, _ in trending_rows:
        pid = str(pid)
        if pid in active_ids and pid not in badges:
            badges[pid] = "Trending"

    for (pid,) in db.query(Product.id).filter(Product.is_active == True, Product.discount_pct >= 15):  # noqa: E712
        pid = str(pid)
        if pid not in badges:
            badges[pid] = "Hot Deal"

    two_weeks_ago = datetime.utcnow() - timedelta(days=14)
    for (pid,) in db.query(Product.id).filter(Product.is_active == True, Product.created_at >= two_weeks_ago):  # noqa: E712
        pid = str(pid)
        if pid not in badges:
            badges[pid] = "New"

    return badges
@router.get("/admin/all", response_model=list[ProductOut])
def list_all_products_admin(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(Product).order_by(Product.created_at.desc()).all()

@router.get("/best-sellers", response_model=list[ProductOut])
def best_sellers(limit: int = 10, db: Session = Depends(get_db)):
    paid_orders = db.query(Order).filter(Order.status == OrderStatus.paid).all()

    quantity_by_product: dict[str, int] = {}
    for order in paid_orders:
        for item in order.items:
            pid = item["product_id"]
            quantity_by_product[pid] = quantity_by_product.get(pid, 0) + item["quantity"]

    ranked_ids = sorted(quantity_by_product, key=lambda pid: quantity_by_product[pid], reverse=True)[:limit]

    if not ranked_ids:
        return (
            db.query(Product)
            .filter(Product.is_active == True)  # noqa: E712
            .order_by(Product.created_at.desc())
            .limit(limit)
            .all()
        )

    products = db.query(Product).filter(Product.id.in_(ranked_ids), Product.is_active == True).all()  # noqa: E712
    products_by_id = {str(p.id): p for p in products}
    return [products_by_id[pid] for pid in ranked_ids if pid in products_by_id]
@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: str, db: Session = Depends(get_db)):
    try:
        uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found.")

    product = db.query(Product).filter(Product.id == product_id, Product.is_active == True).first()  # noqa: E712
    if not product:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found.")
    return product


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: str,
    data: ProductUpdate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found.")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)
    return product