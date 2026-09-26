from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class NotificationOut(BaseModel):
    id: UUID
    type: str
    title: str
    message: str
    link: str | None
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True