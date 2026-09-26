from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.models.wishlist import WishlistItem
from app.models.product import Product
from app.schemas.product import ProductOut

router = APIRouter(prefix="/wishlist", tags=["wishlist"])


@router.post("/{product_id}", status_code=status.HTTP_201_CREATED)
def add_to_wishlist(product_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    existing = (
        db.query(WishlistItem)
        .filter(WishlistItem.user_id == user.id, WishlistItem.product_id == product_id)
        .first()
    )
    if existing:
        return {"ok": True}
    db.add(WishlistItem(user_id=user.id, product_id=product_id))
    db.commit()
    return {"ok": True}


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_wishlist(product_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(WishlistItem).filter(
        WishlistItem.user_id == user.id, WishlistItem.product_id == product_id
    ).delete()
    db.commit()


@router.get("", response_model=list[ProductOut])
def list_wishlist(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(WishlistItem).filter(WishlistItem.user_id == user.id).all()
    product_ids = [i.product_id for i in items]
    if not product_ids:
        return []
    return db.query(Product).filter(Product.id.in_(product_ids)).all()


@router.get("/check/{product_id}")
def check_wishlist(product_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    exists = (
        db.query(WishlistItem)
        .filter(WishlistItem.user_id == user.id, WishlistItem.product_id == product_id)
        .first()
        is not None
    )
    return {"wishlisted": exists}