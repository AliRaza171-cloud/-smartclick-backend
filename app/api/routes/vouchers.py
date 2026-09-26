from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import require_admin, get_db
from app.models.user import User
from app.models.product import Voucher
from app.schemas.product import VoucherCreate, VoucherOut, PublicVoucherOut

router = APIRouter(prefix="/vouchers", tags=["vouchers"])


@router.get("/active", response_model=list[PublicVoucherOut])
def list_active_vouchers(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    vouchers = (
        db.query(Voucher)
        .filter(
            Voucher.is_active == True,  # noqa: E712
            or_(Voucher.expires_at.is_(None), Voucher.expires_at > now),
        )
        .order_by(Voucher.created_at.desc())
        .all()
    )
    return [v for v in vouchers if v.usage_limit is None or v.used_count < v.usage_limit]


@router.post("", response_model=VoucherOut, status_code=status.HTTP_201_CREATED)
def create_voucher(
    data: VoucherCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.query(Voucher).filter(Voucher.code == data.code).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Voucher code {data.code} already exists.")

    voucher = Voucher(**data.model_dump(), created_by=admin.id)
    db.add(voucher)
    db.commit()
    db.refresh(voucher)
    return voucher


@router.get("", response_model=list[VoucherOut])
def list_vouchers(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(Voucher).order_by(Voucher.created_at.desc()).all()


@router.patch("/{code}/deactivate", response_model=VoucherOut)
def deactivate_voucher(code: str, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    voucher = db.query(Voucher).filter(Voucher.code == code.upper()).first()
    if not voucher:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voucher not found.")
    voucher.is_active = False
    db.commit()
    db.refresh(voucher)
    return voucher


@router.get("/{code}/check")
def check_voucher(code: str, db: Session = Depends(get_db)):
    """
    Public — a buyer entering a voucher code at checkout (Phase 6) needs to
    know if it's valid without needing an account or admin rights. Returns
    only what's safe to expose: validity and the discount shape, not who
    created it or how many total uses are allowed.
    """
    voucher = db.query(Voucher).filter(Voucher.code == code.upper()).first()
    if not voucher or not voucher.is_valid:
        return {"valid": False}
    return {
        "valid": True,
        "discount_type": voucher.discount_type,
        "discount_value": voucher.discount_value,
        "min_order_value": voucher.min_order_value,
    }
