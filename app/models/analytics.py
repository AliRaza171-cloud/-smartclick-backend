import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # "page_view" | "product_view" | "add_to_cart" | "add_to_wishlist"
    event_type = Column(String, nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    # Anonymous-visitor identifier (a long-lived cookie) — lets us count
    # unique visitors and their activity even when not logged in.
    session_id = Column(String, nullable=False)
    path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)