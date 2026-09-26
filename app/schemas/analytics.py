from pydantic import BaseModel, field_validator


class TrackEventIn(BaseModel):
    event_type: str
    product_id: str | None = None
    path: str | None = None

    @field_validator("event_type")
    @classmethod
    def valid_event_type(cls, v: str) -> str:
        if v not in ("page_view", "product_view", "add_to_cart", "add_to_wishlist"):
            raise ValueError("invalid event_type")
        return v