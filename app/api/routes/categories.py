import os
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.api.deps import require_admin, get_db
from app.models.user import User
from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryOut
from app.api.routes.products import ALLOWED_CONTENT_TYPES
from app.services import storage_service

router = APIRouter(prefix="/categories", tags=["categories"])


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "category"


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    data: CategoryCreate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.query(Category).filter(Category.name == data.name).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Category '{data.name}' already exists.")

    slug = _slugify(data.name)
    base_slug = slug
    suffix = 2
    while db.query(Category).filter(Category.slug == slug).first():
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    category = Category(name=data.name, slug=slug, tagline=data.tagline)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.get("", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    return db.query(Category).order_by(Category.name).all()


@router.patch("/{slug}/image", response_model=CategoryOut)
async def set_category_image(
    slug: str,
    image: UploadFile = File(...),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    No background removal here on purpose — a category banner should keep
    its full scene (e.g. a styled kitchen counter), not become a cutout
    like a single product photo.
    """
    category = db.query(Category).filter(Category.slug == slug).first()
    if not category:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found.")

    if image.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unsupported file type: {image.content_type}. Use JPEG, PNG, or WebP.",
        )

    ext = os.path.splitext(image.filename or "")[1] or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    category.image_url = storage_service.save_bytes(await image.read(), filename, resource_type="image")
    db.commit()
    db.refresh(category)
    return category