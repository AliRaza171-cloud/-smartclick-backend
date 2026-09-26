from pydantic import BaseModel, field_validator, model_validator
from uuid import UUID
from datetime import datetime
from decimal import Decimal


class ProductCreate(BaseModel):
    title: str
    description: str
    category: str
    price: Decimal
    discount_pct: int | None = None
    free_shipping: bool = False
    voucher_code: str | None = None
    image_urls: list[str]
    video_url: str | None = None
    tags: list[str] = []
    ai_generated: bool = False
    ai_flagged_needs_review: bool = False

    # category is no longer checked against a fixed list here — it's
    # validated against the real `categories` table in the route itself
    # (schemas don't have DB access), so a category just needs to already
    # exist, created via POST /categories first.

    @field_validator("discount_pct")
    @classmethod
    def discount_in_range(cls, v: int | None) -> int | None:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("discount_pct must be between 0 and 100")
        return v

    @field_validator("price")
    @classmethod
    def price_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("price must be greater than 0")
        return v


class ProductUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    price: Decimal | None = None
    discount_pct: int | None = None
    free_shipping: bool | None = None
    voucher_code: str | None = None
    is_active: bool | None = None


class ProductOut(BaseModel):
    id: UUID
    title: str
    description: str
    category: str
    price: Decimal
    discount_pct: int | None
    free_shipping: bool
    voucher_code: str | None
    image_urls: list[str]
    video_url: str | None
    tags: list[str]
    ai_generated: bool
    ai_flagged_needs_review: bool
    is_active: bool
    created_at: datetime
    average_rating: float | None = None
    review_count: int = 0

    class Config:
        from_attributes = True


class VoucherCreate(BaseModel):
    code: str
    discount_type: str  # "percent" | "flat"
    discount_value: Decimal
    min_order_value: Decimal | None = None
    usage_limit: int | None = None
    expires_at: datetime | None = None
    applicable_product_ids: list[UUID] | None = None  # None/empty = entire store
    grants_free_shipping: bool = False

    @field_validator("code")
    @classmethod
    def code_uppercase(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("code cannot be blank")
        return v

    @field_validator("discount_type")
    @classmethod
    def type_valid(cls, v: str) -> str:
        if v not in ("percent", "flat"):
            raise ValueError('discount_type must be "percent" or "flat"')
        return v

    @field_validator("discount_value")
    @classmethod
    def value_not_negative(cls, v: Decimal) -> Decimal:
        # 0 is allowed — a "free shipping only" voucher has no monetary
        # discount at all; the check that a voucher does SOMETHING (a real
        # discount OR grants_free_shipping) happens below.
        if v < 0:
            raise ValueError("discount_value cannot be negative")
        return v

    @model_validator(mode="after")
    def must_do_something(self):
        if self.discount_value == 0 and not self.grants_free_shipping:
            raise ValueError("A voucher needs a discount_value above 0, or grants_free_shipping set.")
        return self

class PublicVoucherOut(BaseModel):
    code: str
    discount_type: str
    discount_value: Decimal
    min_order_value: Decimal | None
    grants_free_shipping: bool
class VoucherOut(BaseModel):
    code: str
    discount_type: str
    discount_value: Decimal
    min_order_value: Decimal | None
    usage_limit: int | None
    used_count: int
    expires_at: datetime | None
    is_active: bool
    applicable_product_ids: list[UUID] | None
    grants_free_shipping: bool
    created_at: datetime

    class Config:
        from_attributes = True