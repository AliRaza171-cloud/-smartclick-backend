# import uuid
# from datetime import datetime

# from sqlalchemy import Column, String, DateTime
# from sqlalchemy.dialects.postgresql import UUID

# from app.db.session import Base


# class Category(Base):
#     __tablename__ = "categories"

#     id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
#     name = Column(String, unique=True, nullable=False)
#     slug = Column(String, unique=True, nullable=False)
#     tagline = Column(String, nullable=True)
#     image_url = Column(String, nullable=True)
#     created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base


class Category(Base):
    __tablename__ = "categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)
    slug = Column(String, unique=True, nullable=False)
    tagline = Column(String, nullable=True)
    image_url = Column(String, nullable=True)
    # Admin-controlled display order on the storefront (lower = first).
    sort_order = Column(Integer, default=0, server_default="0", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)