# from pydantic import BaseModel, field_validator
# from uuid import UUID
# from datetime import datetime


# class CategoryCreate(BaseModel):
#     name: str
#     tagline: str | None = None

#     @field_validator("name")
#     @classmethod
#     def name_not_blank(cls, v: str) -> str:
#         v = v.strip()
#         if not v:
#             raise ValueError("Category name cannot be blank.")
#         return v


# class CategoryOut(BaseModel):
#     id: UUID
#     name: str
#     slug: str
#     tagline: str | None
#     image_url: str | None
#     created_at: datetime

#     class Config:
#         from_attributes = True

from pydantic import BaseModel, field_validator
from uuid import UUID
from datetime import datetime


class CategoryCreate(BaseModel):
    name: str
    tagline: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Category name cannot be blank.")
        return v


class CategoryOut(BaseModel):
    id: UUID
    name: str
    slug: str
    tagline: str | None
    image_url: str | None
    sort_order: int = 0
    created_at: datetime

    class Config:
        from_attributes = True

class CategoryReorder(BaseModel):
    # Every category slug, in the order they should appear on the storefront.
    slugs: list[str]
