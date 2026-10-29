"""Central API router aggregating versioned endpoint routers."""

from fastapi import APIRouter

from app.api.v1 import (
    business,
    conversations,
    customers,
    followups,
    health,
    inquiries,
    knowledge,
    leads,
    products,
)

api_router = APIRouter()

# Include version 1 API endpoints
api_router.include_router(health.router, prefix="/api/v1")
api_router.include_router(business.router, prefix="/api/v1")
api_router.include_router(products.router, prefix="/api/v1")
api_router.include_router(customers.router, prefix="/api/v1")
api_router.include_router(leads.router, prefix="/api/v1")
api_router.include_router(conversations.router, prefix="/api/v1")
api_router.include_router(followups.router, prefix="/api/v1")
api_router.include_router(knowledge.router, prefix="/api/v1")
api_router.include_router(inquiries.router, prefix="/api/v1")
