import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.api.deps import require_admin, get_db
from app.models.hero_image import HeroImage
from app.schemas.hero_image import HeroImageOut
from app.api.routes.products import _strip_background, ALLOWED_CONTENT_TYPES
from app.services import storage_service

router = APIRouter(prefix="/hero-images", tags=["hero-images"])


@router.get("", response_model=list[HeroImageOut])
def list_hero_images(db: Session = Depends(get_db)):
    return db.query(HeroImage).order_by(HeroImage.sort_order, HeroImage.created_at).all()


@router.post("", response_model=list[HeroImageOut], status_code=status.HTTP_201_CREATED)
async def upload_hero_images(
    images: list[UploadFile] = File(...),
    remove_bg: bool = Form(True),
    placement: str = Form("carousel"),
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not images:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "At least one image is required.")
    if placement not in ("carousel", "strip"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, 'placement must be "carousel" or "strip".')

    existing_count = db.query(HeroImage).filter(HeroImage.placement == placement).count()
    created = []

    for i, image in enumerate(images):
        if image.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Unsupported file type: {image.content_type}. Use JPEG, PNG, or WebP.",
            )
        raw_bytes = image.file.read()

        if remove_bg:
            try:
                raw_bytes = _strip_background(raw_bytes)
                ext = ".png"
            except Exception as e:
                print(f"[hero_images] Background removal failed, keeping original: {e}")
                ext = os.path.splitext(image.filename or "")[1] or ".jpg"
        else:
            ext = os.path.splitext(image.filename or "")[1] or ".jpg"
        filename = f"{uuid.uuid4().hex}{ext}"
        image_url = storage_service.save_bytes(raw_bytes, filename, resource_type="image")

        hero_image = HeroImage(image_url=image_url, placement=placement, sort_order=existing_count + i)
        db.add(hero_image)
        created.append(hero_image)

    db.commit()
    for h in created:
        db.refresh(h)
    return created


@router.delete("/{hero_image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_hero_image(hero_image_id: str, _admin=Depends(require_admin), db: Session = Depends(get_db)):
    hero_image = db.query(HeroImage).filter(HeroImage.id == hero_image_id).first()
    if hero_image:
        storage_service.delete_by_url(hero_image.image_url)
    db.query(HeroImage).filter(HeroImage.id == hero_image_id).delete()
    db.commit()