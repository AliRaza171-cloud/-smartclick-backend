import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base


class HeroImage(Base):
    __tablename__ = "hero_images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    image_url = Column(String, nullable=False)
    placement = Column(String, default="carousel", nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)