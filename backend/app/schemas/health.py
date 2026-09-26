"""Health and readiness endpoint response schemas."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness probe response model."""

    status: str = Field(default="ok", description="Liveness status")
    service: str = Field(default="ai-business-automation", description="Service identifier")
    version: str = Field(default="0.1.0", description="Application version")


class ReadinessResponse(BaseModel):
    """Readiness probe response model checking dependent components."""

    status: str = Field(..., description="Readiness status ('ready' or 'not_ready')")
    dependencies: dict[str, str] = Field(
        ..., description="Health status of external dependencies (e.g. database)"
    )
