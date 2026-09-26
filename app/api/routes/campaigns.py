from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

from app.api.deps import require_admin, get_db
from app.models.user import User
from app.models.campaign import SaleCampaign
from app.schemas.campaign import CampaignCreate, CampaignOut, PublicCampaignOut

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("/active", response_model=list[PublicCampaignOut])
def list_active_campaigns(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    return (
        db.query(SaleCampaign)
        .filter(
            SaleCampaign.is_active == True,  # noqa: E712
            or_(SaleCampaign.start_at.is_(None), SaleCampaign.start_at <= now),
            or_(SaleCampaign.end_at.is_(None), SaleCampaign.end_at >= now),
        )
        .order_by(SaleCampaign.created_at.desc())
        .all()
    )


@router.get("", response_model=list[CampaignOut])
def list_all_campaigns(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(SaleCampaign).order_by(SaleCampaign.created_at.desc()).all()


@router.post("", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
def create_campaign(
    data: CampaignCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    campaign = SaleCampaign(
        message=data.message, start_at=data.start_at, end_at=data.end_at, created_by=admin.id
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


@router.patch("/{campaign_id}/deactivate", response_model=CampaignOut)
def deactivate_campaign(
    campaign_id: str, _admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    campaign = db.query(SaleCampaign).filter(SaleCampaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found.")
    campaign.is_active = False
    db.commit()
    db.refresh(campaign)
    return campaign


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_campaign(campaign_id: str, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    db.query(SaleCampaign).filter(SaleCampaign.id == campaign_id).delete()
    db.commit()