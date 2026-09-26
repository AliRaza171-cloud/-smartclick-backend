import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base


class NewsletterSubscriber(Base):
    __tablename__ = "newsletter_subscribers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, nullable=False, unique=True)
    subscribed_at = Column(DateTime, default=datetime.utcnow, nullable=False)