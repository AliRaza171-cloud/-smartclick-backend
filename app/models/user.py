import uuid
import enum
from datetime import datetime

from sqlalchemy import Column, String, Boolean, DateTime, Integer, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class UserRole(str, enum.Enum):
    buyer = "buyer"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=True)  # nullable: OAuth-only users have no password
    full_name = Column(String, nullable=True)
    role = Column(Enum(UserRole), default=UserRole.buyer, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)
    is_email_verified = Column(Boolean, default=False, nullable=False)

    # OAuth
    google_id = Column(String, unique=True, nullable=True, index=True)

    # Brute-force protection
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")


class RefreshToken(Base):
    """
    Each row is one issued refresh token (hashed, never stored raw).
    Rotation: on every /auth/refresh call we revoke this row and issue a new
    one with the same `family_id`. If a revoked token is ever presented again
    (a sign of theft — the real user already rotated past it), we revoke the
    ENTIRE family, forcing re-login everywhere that session tree was used.
    """
    __tablename__ = "refresh_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    selector = Column(String, unique=True, index=True, nullable=False)  # O(1) lookup, safe if leaked alone
    verifier_hash = Column(String, nullable=False)                       # the actual secret, hashed
    family_id = Column(UUID(as_uuid=True), nullable=False)  # shared across a rotation chain
    revoked = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    user_agent = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)

    user = relationship("User", back_populates="refresh_tokens")
