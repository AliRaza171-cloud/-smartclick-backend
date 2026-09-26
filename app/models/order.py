import uuid
import enum
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Numeric, Boolean, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.db.session import Base


class OrderStatus(str, enum.Enum):
    pending_payment = "pending_payment"
    paid = "paid"
    cancelled = "cancelled"


class PaymentMethod(str, enum.Enum):
    cod = "cod"
    easypaisa = "easypaisa"  # legacy — kept only so old rows still deserialize; no longer offered at checkout
    jazzcash = "jazzcash"    # legacy — same as above
    card = "card"            # Stripe
    safepay = "safepay"      # JazzCash / EasyPaisa / any Pakistani bank card, via Safepay's hosted checkout


class FulfillmentStatus(str, enum.Enum):
    """
    Separate from OrderStatus (payment) on purpose — a paid order can sit
    at any fulfillment stage, and a not-yet-paid order can still be getting
    prepared in some businesses. Keeping these as two independent fields
    avoids an awkward combined enum like "paid_and_ready_to_ship".
    """
    pending = "pending"
    ready_to_ship = "ready_to_ship"
    shipped = "shipped"
    delivered = "delivered"

class OrderMessage(Base):
    __tablename__ = "order_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    sender_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    sender_role = Column(String, nullable=False)
    message = Column(String, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    sender = relationship("User")


class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Snapshot of cart items at purchase time (product_id, title, unit_price,
    # quantity, image_url) — deliberately NOT a live join to products, so a
    # later price change or deleted product never rewrites past order history.
    items = Column(JSONB, nullable=False)

    subtotal = Column(Numeric(10, 2), nullable=False)
    voucher_code = Column(String, ForeignKey("vouchers.code"), nullable=True)
    discount_amount = Column(Numeric(10, 2), default=0, nullable=False)
    free_shipping = Column(Boolean, default=False, nullable=False)
    total = Column(Numeric(10, 2), nullable=False)

    payment_method = Column(Enum(PaymentMethod), nullable=False)
    # Only meaningful for cod — a flat surcharge for the extra handling a
    # cash pickup requires. Stored explicitly (not just folded into total)
    # so the buyer's order summary and email can show it as its own line.
    cod_fee = Column(Numeric(10, 2), default=0, nullable=False)
    stripe_checkout_session_id = Column(String, nullable=True)
    safepay_token = Column(String, nullable=True)

    shipping_name = Column(String, nullable=False)
    shipping_phone = Column(String, nullable=False)
    shipping_address = Column(String, nullable=False)
    shipping_city = Column(String, nullable=False)

    status = Column(Enum(OrderStatus), default=OrderStatus.pending_payment, nullable=False)
    fulfillment_status = Column(Enum(FulfillmentStatus), default=FulfillmentStatus.pending, nullable=False)
    cancellation_requested = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User")