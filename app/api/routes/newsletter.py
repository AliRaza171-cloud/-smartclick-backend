from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.newsletter import NewsletterSubscriber

router = APIRouter(prefix="/newsletter", tags=["newsletter"])


class SubscribeRequest(BaseModel):
    email: EmailStr


@router.post("/subscribe", status_code=204)
def subscribe(data: SubscribeRequest, db: Session = Depends(get_db)):
    existing = db.query(NewsletterSubscriber).filter(NewsletterSubscriber.email == data.email).first()
    if not existing:
        db.add(NewsletterSubscriber(email=data.email))
        db.commit()