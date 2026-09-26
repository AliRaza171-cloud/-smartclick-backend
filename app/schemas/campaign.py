# from pydantic import BaseModel, field_validator
# from uuid import UUID
# from datetime import datetime


# class CampaignCreate(BaseModel):
#     message: str
#     start_at: datetime | None = None
#     end_at: datetime | None = None

#     @field_validator("message")
#     @classmethod
#     def message_not_empty(cls, v: str) -> str:
#         if not v.strip():
#             raise ValueError("Message cannot be empty.")
#         return v.strip()


# class CampaignOut(BaseModel):
#     id: UUID
#     message: str
#     is_active: bool
#     start_at: datetime | None
#     end_at: datetime | None
#     created_at: datetime

#     class Config:
#         from_attributes = True


# class PublicCampaignOut(BaseModel):
#     message: str

#     class Config:
#         from_attributes = True
from pydantic import BaseModel, field_validator, model_validator
from uuid import UUID
from datetime import datetime, timezone


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

    @field_validator("start_at", "end_at")
    @classmethod
    def to_naive_utc(cls, v: datetime | None) -> datetime | None:
        # The DB column is a naive timestamp compared against datetime.utcnow(),
        # so store everything as naive UTC. The admin form sends a timezone-aware
        # ISO string; an old-style naive value is assumed to already be UTC.
        if v is not None and v.tzinfo is not None:
            v = v.astimezone(timezone.utc).replace(tzinfo=None)
        return v

    @model_validator(mode="after")
    def end_after_start(self):
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValueError("End time must be after the start time.")
        return self


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
    # Naive UTC (see CampaignCreate) — the storefront countdown treats it as UTC.
    end_at: datetime | None = None

    class Config:
        from_attributes = True