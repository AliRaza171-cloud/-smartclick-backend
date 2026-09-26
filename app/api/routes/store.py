from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(prefix="/store-info", tags=["store"])


@router.get("")
def get_store_info():
    """
    Public — this is just the store's own mailing address/phone, the "from"
    side of every shipping label. Nothing sensitive; the frontend needs it
    to render a label without duplicating the store's address in two places.
    """
    return {
        "name": settings.STORE_NAME,
        "address": settings.STORE_ADDRESS,
        "city": settings.STORE_CITY,
        "phone": settings.STORE_PHONE,
    }