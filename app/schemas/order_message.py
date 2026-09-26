from pydantic import BaseModel, field_validator
from uuid import UUID
from datetime import datetime


class OrderMessageCreate(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Message cannot be empty.")
        return v.strip()


class OrderMessageOut(BaseModel):
    id: UUID
    order_id: UUID
    sender_role: str
    sender_name: str
    message: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class CancellationDecision(BaseModel):
    approve: bool