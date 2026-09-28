# import os
# import re
# import uuid

# from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
# from sqlalchemy.orm import Session

# from app.core.config import settings
# from app.api.deps import require_admin, get_db
# from app.models.user import User
# from app.models.category import Category
# from app.schemas.category import CategoryCreate, CategoryOut
# from app.api.routes.products import ALLOWED_CONTENT_TYPES
# from app.services import storage_service

# router = APIRouter(prefix="/categories", tags=["categories"])


# def _slugify(name: str) -> str:
#     slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
#     return slug or "category"


# @router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
# def create_category(
#     data: CategoryCreate,
#     _admin: User = Depends(require_admin),
#     db: Session = Depends(get_db),
# ):
#     if db.query(Category).filter(Category.name == data.name).first():
#         raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Category '{data.name}' already exists.")

#     slug = _slugify(data.name)
#     base_slug = slug
#     suffix = 2
#     while db.query(Category).filter(Category.slug == slug).first():
#         slug = f"{base_slug}-{suffix}"
#         suffix += 1

#     category = Category(name=data.name, slug=slug, tagline=data.tagline)
#     db.add(category)
#     db.commit()
#     db.refresh(category)
#     return category


# @router.get("", response_model=list[CategoryOut])
# def list_categories(db: Session = Depends(get_db)):
#     return db.query(Category).order_by(Category.name).all()


# @router.patch("/{slug}/image", response_model=CategoryOut)
# async def set_category_image(
#     slug: str,
#     image: UploadFile = File(...),
#     _admin: User = Depends(require_admin),
#     db: Session = Depends(get_db),
# ):
#     """
#     No background removal here on purpose — a category banner should keep
#     its full scene (e.g. a styled kitchen counter), not become a cutout
#     like a single product photo.
#     """
#     category = db.query(Category).filter(Category.slug == slug).first()
#     if not category:
#         raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found.")

#     if image.content_type not in ALLOWED_CONTENT_TYPES:
#         raise HTTPException(
#             status.HTTP_400_BAD_REQUEST,
#             f"Unsupported file type: {image.content_type}. Use JPEG, PNG, or WebP.",
#         )

#     ext = os.path.splitext(image.filename or "")[1] or ".jpg"
#     filename = f"{uuid.uuid4().hex}{ext}"
#     category.image_url = storage_service.save_bytes(await image.read(), filename, resource_type="image")
#     db.commit()
#     db.refresh(category)
#     return category

import os
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.api.deps import require_admin, get_db
from app.models.user import User
from app.models.category import Category
from app.models.product import Product
from app.schemas.category import CategoryCreate, CategoryOut, CategoryReorder, CategoryUpdate
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

    # New categories go to the end of the admin-defined order.
    next_order = (db.query(func.max(Category.sort_order)).scalar() or 0) + 1
    category = Category(name=data.name, slug=slug, tagline=data.tagline, sort_order=next_order)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.get("", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    # Admin-defined order first; name keeps it stable for ties (e.g. before
    # any reordering has happened, everything is sort_order 0 -> alphabetical).
    return db.query(Category).order_by(Category.sort_order, Category.name).all()


@router.patch("/order", response_model=list[CategoryOut])
def reorder_categories(
    data: CategoryReorder,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    categories = {c.slug: c for c in db.query(Category).all()}
    if len(set(data.slugs)) != len(data.slugs):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Duplicate category in the new order.")
    unknown = [s for s in data.slugs if s not in categories]
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown category: {', '.join(unknown)}")

    for index, slug in enumerate(data.slugs):
        categories[slug].sort_order = index
    # Any category left out of the request (e.g. created meanwhile) keeps its
    # relative place after the ones that were ordered.
    leftovers = sorted((c for s, c in categories.items() if s not in data.slugs), key=lambda c: (c.sort_order, c.name))
    for offset, c in enumerate(leftovers):
        c.sort_order = len(data.slugs) + offset

    db.commit()
    return db.query(Category).order_by(Category.sort_order, Category.name).all()


@router.patch("/{slug}", response_model=CategoryOut)
def update_category(
    slug: str,
    data: CategoryUpdate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Rename a category (and/or change its tagline).

    Products refer to their category by name, so a rename moves every product in it
    to the new name in the same transaction. The slug (the /category/<slug> web
    address) is rebuilt from the new name so it keeps matching.
    """
    category = db.query(Category).filter(Category.slug == slug).first()
    if not category:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found.")

    fields = data.model_dump(exclude_unset=True)

    new_name = fields.get("name")
    if new_name is not None and new_name != category.name:
        clash = (
            db.query(Category)
            .filter(func.lower(Category.name) == new_name.lower(), Category.id != category.id)
            .first()
        )
        if clash:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"A category called '{clash.name}' already exists.")

        old_name = category.name
        db.query(Product).filter(Product.category == old_name).update(
            {Product.category: new_name}, synchronize_session=False
        )
        category.name = new_name

        base = _slugify(new_name)
        new_slug, suffix = base, 2
        while db.query(Category).filter(Category.slug == new_slug, Category.id != category.id).first():
            new_slug = f"{base}-{suffix}"
            suffix += 1
        category.slug = new_slug

    if "tagline" in fields:
        category.tagline = fields["tagline"] or None

    db.commit()
    db.refresh(category)
    return category


@router.patch("/{slug}", response_model=CategoryOut)
def update_category(
    slug: str,
    data: CategoryUpdate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Rename a category (and/or change its tagline).

    Products refer to their category by name, so a rename moves every product in it
    to the new name in the same transaction. The slug (the /category/<slug> web
    address) is rebuilt from the new name so it keeps matching.
    """
    category = db.query(Category).filter(Category.slug == slug).first()
    if not category:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found.")

    fields = data.model_dump(exclude_unset=True)

    new_name = fields.get("name")
    if new_name is not None and new_name != category.name:
        clash = (
            db.query(Category)
            .filter(func.lower(Category.name) == new_name.lower(), Category.id != category.id)
            .first()
        )
        if clash:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"A category called '{clash.name}' already exists.")

        old_name = category.name
        db.query(Product).filter(Product.category == old_name).update(
            {Product.category: new_name}, synchronize_session=False
        )
        category.name = new_name

        base = _slugify(new_name)
        new_slug, suffix = base, 2
        while db.query(Category).filter(Category.slug == new_slug, Category.id != category.id).first():
            new_slug = f"{base}-{suffix}"
            suffix += 1
        category.slug = new_slug

    if "tagline" in fields:
        category.tagline = fields["tagline"] or None

    db.commit()
    db.refresh(category)
    return category


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