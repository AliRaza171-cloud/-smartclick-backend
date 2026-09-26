import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base


class SaleCampaign(Base):
    __tablename__ = "sale_campaigns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    start_at = Column(DateTime, nullable=True)
    end_at = Column(DateTime, nullable=True)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)