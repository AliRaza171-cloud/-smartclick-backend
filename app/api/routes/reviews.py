from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.models.order import Order, FulfillmentStatus
from app.models.review import Review
from app.schemas.review import ReviewCreate, ReviewOut, ReviewSummary

router = APIRouter(prefix="/products", tags=["reviews"])


def _order_contains_product(order: Order, product_id: str) -> bool:
    return any(item["product_id"] == product_id for item in order.items)


@router.get("/{product_id}/reviews", response_model=list[ReviewOut])
def list_reviews(product_id: str, db: Session = Depends(get_db)):
    reviews = (
        db.query(Review)
        .filter(Review.product_id == product_id)
        .order_by(Review.created_at.desc())
        .all()
    )
    return [
        ReviewOut(
            id=r.id,
            rating=r.rating,
            comment=r.comment,
            created_at=r.created_at,
            reviewer_name=(r.user.full_name or r.user.email.split("@")[0]) if r.user else "Buyer",
        )
        for r in reviews
    ]


@router.get("/{product_id}/reviews/summary", response_model=ReviewSummary)
def review_summary(product_id: str, db: Session = Depends(get_db)):
    result = (
        db.query(func.avg(Review.rating), func.count(Review.id))
        .filter(Review.product_id == product_id)
        .first()
    )
    avg_rating, count = result
    return ReviewSummary(
        average_rating=round(float(avg_rating), 1) if avg_rating is not None else None,
        review_count=count or 0,
    )


@router.get("/{product_id}/reviews/eligibility")
def review_eligibility(
    product_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    already_reviewed = (
        db.query(Review).filter(Review.user_id == user.id, Review.product_id == product_id).first()
        is not None
    )
    if already_reviewed:
        return {"can_review": False, "reason": "already_reviewed", "order_id": None}

    shipped_orders = (
        db.query(Order)
        .filter(Order.user_id == user.id, Order.fulfillment_status == FulfillmentStatus.shipped)
        .order_by(Order.created_at.desc())
        .all()
    )
    for order in shipped_orders:
        if _order_contains_product(order, product_id):
            return {"can_review": True, "reason": None, "order_id": str(order.id)}

    return {"can_review": False, "reason": "no_shipped_order", "order_id": None}


@router.post("/{product_id}/reviews", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def create_review(
    product_id: str,
    data: ReviewCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if db.query(Review).filter(Review.user_id == user.id, Review.product_id == product_id).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You've already reviewed this product.")

    order = db.query(Order).filter(Order.id == data.order_id, Order.user_id == user.id).first()
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")
    if order.fulfillment_status != FulfillmentStatus.shipped:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "You can only review a product after your order has shipped."
        )
    if not _order_contains_product(order, product_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This order doesn't contain that product.")

    review = Review(
        product_id=product_id,
        user_id=user.id,
        order_id=order.id,
        rating=data.rating,
        comment=data.comment,
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    return ReviewOut(
        id=review.id,
        rating=review.rating,
        comment=review.comment,
        created_at=review.created_at,
        reviewer_name=user.full_name or user.email.split("@")[0],
    )