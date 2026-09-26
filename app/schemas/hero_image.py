from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class HeroImageOut(BaseModel):
    id: UUID
    image_url: str
    placement: str
    sort_order: int
    created_at: datetime

    class Config:
        from_attributes = True