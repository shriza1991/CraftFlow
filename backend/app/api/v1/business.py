"""Public business context for the configured deployment."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(prefix="/business", tags=["Business"])


class BusinessProfile(BaseModel):
    name: str
    description: str
    industry: str


@router.get("", response_model=BusinessProfile)
def get_business() -> BusinessProfile:
    settings = get_settings()
    return BusinessProfile(
        name=settings.BUSINESS_NAME,
        description=settings.BUSINESS_DESCRIPTION,
        industry=settings.BUSINESS_INDUSTRY,
    )
