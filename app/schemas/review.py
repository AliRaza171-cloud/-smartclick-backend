from pydantic import BaseModel, field_validator
from uuid import UUID
from datetime import datetime


class ReviewCreate(BaseModel):
    order_id: UUID
    rating: int
    comment: str | None = None

    @field_validator("rating")
    @classmethod
    def rating_in_range(cls, v: int) -> int:
        if v < 1 or v > 5:
            raise ValueError("rating must be between 1 and 5")
        return v


class ReviewOut(BaseModel):
    id: UUID
    rating: int
    comment: str | None
    created_at: datetime
    reviewer_name: str

    class Config:
        from_attributes = True


class ReviewSummary(BaseModel):
    average_rating: float | None
    review_count: int