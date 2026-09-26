"""Health and Readiness endpoints."""

from fastapi import APIRouter, Response, status

from app.core.config import get_settings
from app.db.session import check_database_connectivity
from app.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter(tags=["Health & Diagnostics"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness Health Check",
    description="Returns service liveness status. Does not require database or external dependencies.",
    status_code=status.HTTP_200_OK,
)
async def get_health() -> HealthResponse:
    """Liveness probe indicating the HTTP application is alive and accepting traffic."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service="ai-business-automation",
        version=settings.APP_VERSION,
    )


@router.get(
    "/readiness",
    response_model=ReadinessResponse,
    summary="Readiness Check",
    description="Verifies operational readiness of critical dependencies including PostgreSQL.",
    responses={
        200: {
            "description": "Service and all dependencies are healthy and ready to serve traffic."
        },
        503: {"description": "Service dependencies are unavailable or failing."},
    },
)
async def get_readiness(response: Response) -> ReadinessResponse:
    """Readiness probe checking database connectivity."""
    db_healthy = check_database_connectivity()

    dependencies = {
        "database": "healthy" if db_healthy else "unhealthy",
    }

    if not db_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(status="not_ready", dependencies=dependencies)

    return ReadinessResponse(status="ready", dependencies=dependencies)
