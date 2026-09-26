from pydantic import BaseModel, field_validator
from uuid import UUID
from datetime import datetime
from decimal import Decimal


class CartItemIn(BaseModel):
    product_id: UUID
    quantity: int

    @field_validator("quantity")
    @classmethod
    def quantity_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("quantity must be at least 1")
        return v


class OrderCreate(BaseModel):
    items: list[CartItemIn]
    voucher_code: str | None = None
    shipping_name: str
    shipping_phone: str
    shipping_address: str
    shipping_city: str
    payment_method: str

    @field_validator("items")
    @classmethod
    def items_not_empty(cls, v: list[CartItemIn]) -> list[CartItemIn]:
        if not v:
            raise ValueError("Cart cannot be empty.")
        return v

    @field_validator("payment_method")
    @classmethod
    def valid_payment_method(cls, v: str) -> str:
        if v not in ("cod", "card", "safepay"):
            raise ValueError('payment_method must be "cod", "card", or "safepay"')
        return v


class OrderItemOut(BaseModel):
    product_id: str
    title: str
    unit_price: Decimal
    quantity: int
    image_url: str | None = None


class OrderOut(BaseModel):
    id: UUID
    items: list[OrderItemOut]
    subtotal: Decimal
    voucher_code: str | None
    discount_amount: Decimal
    free_shipping: bool
    total: Decimal
    payment_method: str
    cod_fee: Decimal
    shipping_name: str
    shipping_phone: str
    shipping_address: str
    shipping_city: str
    status: str
    fulfillment_status: str
    cancellation_requested: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class FulfillmentStatusUpdate(BaseModel):
    fulfillment_status: str

    @field_validator("fulfillment_status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        if v not in ("pending", "ready_to_ship", "shipped"):
            raise ValueError('fulfillment_status must be "pending", "ready_to_ship", or "shipped"')
        return v