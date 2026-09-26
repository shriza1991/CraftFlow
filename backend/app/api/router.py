"""Central API router aggregating versioned endpoint routers."""

from fastapi import APIRouter

from app.api.v1 import health

api_router = APIRouter()

# Include version 1 API endpoints
api_router.include_router(health.router, prefix="/api/v1")
