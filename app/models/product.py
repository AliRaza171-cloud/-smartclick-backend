# import uuid
# import enum
# from datetime import datetime

# from sqlalchemy import Column, String, Boolean, DateTime, Integer, Numeric, ForeignKey, Enum
# from sqlalchemy.dialects.postgresql import UUID, ARRAY
# from sqlalchemy.orm import relationship

# from app.db.session import Base


# class DiscountType(str, enum.Enum):
#     percent = "percent"
#     flat = "flat"


# class Product(Base):
#     __tablename__ = "products"

#     id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

#     title = Column(String, nullable=False)
#     description = Column(String, nullable=False)
#     category = Column(String, nullable=False)  # validated against the fixed taxonomy in the schema layer

#     price = Column(Numeric(10, 2), nullable=False)
#     discount_pct = Column(Integer, nullable=True)  # 0-100, nullable = no discount
#     free_shipping = Column(Boolean, default=False, nullable=False)
#     voucher_code = Column(String, ForeignKey("vouchers.code"), nullable=True)

#     image_urls = Column(ARRAY(String), nullable=False, default=list)
#     video_url = Column(String, nullable=True)
#     tags = Column(ARRAY(String), nullable=False, default=list)

#     # Provenance from the AI Agent service (Phase 4) — kept even after the
#     # seller edits the draft, so it's visible in an admin view which listings
#     # were AI-flagged as needing a closer look before they went live.
#     ai_generated = Column(Boolean, default=False, nullable=False)
#     ai_flagged_needs_review = Column(Boolean, default=False, nullable=False)

#     is_active = Column(Boolean, default=True, nullable=False)  # soft-delete / hide from storefront

#     created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
#     created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
#     updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

#     voucher = relationship("Voucher", back_populates="products")


# class Voucher(Base):
#     __tablename__ = "vouchers"

#     code = Column(String, primary_key=True)  # uppercase, unique — used as the natural key
#     discount_type = Column(Enum(DiscountType), nullable=False)
#     discount_value = Column(Numeric(10, 2), nullable=False)  # percent (0-100) or flat amount depending on type
#     min_order_value = Column(Numeric(10, 2), nullable=True)
#     usage_limit = Column(Integer, nullable=True)  # nullable = unlimited
#     used_count = Column(Integer, default=0, nullable=False)
#     expires_at = Column(DateTime, nullable=True)
#     is_active = Column(Boolean, default=True, nullable=False)

#     # Nullable/empty = applies store-wide. If set, the discount only ever
#     # applies to the subtotal of matching line items in the cart, not the
#     # whole order — checked in orders.py's create_order.
#     applicable_product_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=True)
#     # Independent of any product's own free_shipping flag — this lets a
#     # voucher grant free shipping on its own, e.g. "FREESHIP" with no
#     # discount at all (discount_value can be a nominal amount like 0.01 if
#     # the schema requires >0, or genuinely paired with a real discount too).
#     grants_free_shipping = Column(Boolean, default=False, nullable=False)

#     created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
#     created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

#     products = relationship("Product", back_populates="voucher")

#     @property
#     def is_valid(self) -> bool:
#         if not self.is_active:
#             return False
#         if self.expires_at and self.expires_at < datetime.utcnow():
#             return False
#         if self.usage_limit is not None and self.used_count >= self.usage_limit:
#             return False
#         return True

import uuid
import enum
from datetime import datetime

from sqlalchemy import Column, String, Boolean, DateTime, Integer, Numeric, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship

from app.db.session import Base


class DiscountType(str, enum.Enum):
    percent = "percent"
    flat = "flat"


class Product(Base):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    title = Column(String, nullable=False)
    description = Column(String, nullable=False)
    category = Column(String, nullable=False)  # validated against the fixed taxonomy in the schema layer

    price = Column(Numeric(10, 2), nullable=False)
    discount_pct = Column(Integer, nullable=True)  # 0-100, nullable = no discount
    free_shipping = Column(Boolean, default=False, nullable=False)
    voucher_code = Column(String, ForeignKey("vouchers.code"), nullable=True)

    image_urls = Column(ARRAY(String), nullable=False, default=list)
    video_url = Column(String, nullable=True)
    tags = Column(ARRAY(String), nullable=False, default=list)

    # Provenance from the AI Agent service (Phase 4) — kept even after the
    # seller edits the draft, so it's visible in an admin view which listings
    # were AI-flagged as needing a closer look before they went live.
    ai_generated = Column(Boolean, default=False, nullable=False)
    ai_flagged_needs_review = Column(Boolean, default=False, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)  # soft-delete / hide from storefront

    # Hand-picked by the admin to be pinned at the top of the storefront's
    # Flash Deals section (only meaningful when discount_pct is set).
    is_flash_deal = Column(Boolean, default=False, server_default="false", nullable=False)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    voucher = relationship("Voucher", back_populates="products")


class Voucher(Base):
    __tablename__ = "vouchers"

    code = Column(String, primary_key=True)  # uppercase, unique — used as the natural key
    discount_type = Column(Enum(DiscountType), nullable=False)
    discount_value = Column(Numeric(10, 2), nullable=False)  # percent (0-100) or flat amount depending on type
    min_order_value = Column(Numeric(10, 2), nullable=True)
    usage_limit = Column(Integer, nullable=True)  # nullable = unlimited
    used_count = Column(Integer, default=0, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # Nullable/empty = applies store-wide. If set, the discount only ever
    # applies to the subtotal of matching line items in the cart, not the
    # whole order — checked in orders.py's create_order.
    applicable_product_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=True)
    # Independent of any product's own free_shipping flag — this lets a
    # voucher grant free shipping on its own, e.g. "FREESHIP" with no
    # discount at all (discount_value can be a nominal amount like 0.01 if
    # the schema requires >0, or genuinely paired with a real discount too).
    grants_free_shipping = Column(Boolean, default=False, nullable=False)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    products = relationship("Product", back_populates="voucher")

    @property
    def is_valid(self) -> bool:
        if not self.is_active:
            return False
        if self.expires_at and self.expires_at < datetime.utcnow():
            return False
        if self.usage_limit is not None and self.used_count >= self.usage_limit:
            return False
        return True