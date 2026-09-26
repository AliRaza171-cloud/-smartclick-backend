import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps import get_db, require_admin
from app.core.security import decode_access_token
from app.models.analytics import AnalyticsEvent
from app.models.product import Product
from app.schemas.analytics import TrackEventIn

router = APIRouter(prefix="/analytics", tags=["analytics"])

SESSION_COOKIE = "smartclick_session"


def _get_or_create_session_id(request: Request, response: Response) -> str:
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid:
        sid = uuid.uuid4().hex
        response.set_cookie(
            SESSION_COOKIE, sid, max_age=365 * 24 * 3600, httponly=True, samesite="lax"
        )
    return sid


@router.post("/track", status_code=204)
def track_event(data: TrackEventIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Public — has to work for anonymous, not-logged-in visitors too, which is
    most of a store's traffic. Identifies a logged-in user opportunistically
    from the Authorization header if present, but never requires it.
    """
    session_id = _get_or_create_session_id(request, response)

    user_id = None
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        payload = decode_access_token(auth.split(" ", 1)[1])
        if payload:
            user_id = payload.get("sub")

    db.add(AnalyticsEvent(
        event_type=data.event_type,
        product_id=data.product_id,
        user_id=user_id,
        session_id=session_id,
        path=data.path,
    ))
    db.commit()


def _top_products(db: Session, event_type: str, limit: int = 10):
    rows = (
        db.query(AnalyticsEvent.product_id, func.count(AnalyticsEvent.id).label("count"))
        .filter(AnalyticsEvent.event_type == event_type, AnalyticsEvent.product_id.isnot(None))
        .group_by(AnalyticsEvent.product_id)
        .order_by(func.count(AnalyticsEvent.id).desc())
        .limit(limit)
        .all()
    )
    results = []
    for product_id, count in rows:
        product = db.query(Product).filter(Product.id == product_id).first()
        if product:
            results.append({"product_id": str(product_id), "title": product.title, "count": count})
    return results


@router.get("/summary")
def analytics_summary(_admin=Depends(require_admin), db: Session = Depends(get_db)):
    total_unique_visitors = (
        db.query(func.count(func.distinct(AnalyticsEvent.session_id)))
        .filter(AnalyticsEvent.event_type == "page_view")
        .scalar()
        or 0
    )
    total_page_views = db.query(AnalyticsEvent).filter(AnalyticsEvent.event_type == "page_view").count()

    return {
        "total_unique_visitors": total_unique_visitors,
        "total_page_views": total_page_views,
        "most_viewed_products": _top_products(db, "product_view"),
        "most_added_to_cart": _top_products(db, "add_to_cart"),
        "most_wishlisted": _top_products(db, "add_to_wishlist"),
    }