from pydantic import BaseModel, field_validator
from uuid import UUID
from datetime import datetime


class CampaignCreate(BaseModel):
    message: str
    start_at: datetime | None = None
    end_at: datetime | None = None

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Message cannot be empty.")
        return v.strip()


class CampaignOut(BaseModel):
    id: UUID
    message: str
    is_active: bool
    start_at: datetime | None
    end_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class PublicCampaignOut(BaseModel):
    message: str

    class Config:
        from_attributes = True