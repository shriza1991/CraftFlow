"""FastAPI Application Entry Point."""

import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.agents.demo import DemoAgent
from app.agents.registry import get_agent_registry
from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.logging import get_logger, request_id_ctx, setup_logging
from app.schemas.common import ErrorDetail, ErrorResponse
from app.tools.demo import HealthCheckTool, MockProductSearchTool
from app.tools.registry import get_tool_registry

logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context managing startup initialization and graceful shutdown."""
    settings = get_settings()

    # 1. Initialize logging
    setup_logging(log_level=settings.LOG_LEVEL, service_name="ai-business-automation")
    logger.info("Application starting up...", extra={"event": "startup", "request_id": "system"})

    # 2. Register scaffolding tools and agents for P0 baseline validation
    tool_reg = get_tool_registry()
    try:
        tool_reg.register(MockProductSearchTool())
        tool_reg.register(HealthCheckTool())
    except Exception as exc:
        logger.debug(f"Tools already registered: {exc}")

    agent_reg = get_agent_registry()
    try:
        agent_reg.register(DemoAgent())
    except Exception as exc:
        logger.debug(f"Agents already registered: {exc}")

    logger.info(
        "P0 Scaffolding tools and demo agent registered successfully.", extra={"event": "startup"}
    )

    yield

    # Shutdown logic
    logger.info("Application shutting down...", extra={"event": "shutdown", "request_id": "system"})


def create_application() -> FastAPI:
    """FastAPI application factory with middleware, routers, and centralized exception handling."""
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Configurable AI business automation platform",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --------------------------------------------------------------------------
    # Request Correlation & Timing Middleware
    # --------------------------------------------------------------------------
    @app.middleware("http")
    async def correlation_and_logging_middleware(request: Request, call_next):
        # Extract or generate correlation ID
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = req_id
        token = request_id_ctx.set(req_id)

        start_time = time.perf_counter()
        logger.info(
            f"Incoming request {request.method} {request.url.path}",
            extra={"event": "request_started", "request_id": req_id},
        )

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000
            response.headers["X-Request-ID"] = req_id

            logger.info(
                f"Completed request {request.method} {request.url.path} with status {response.status_code} in {duration_ms:.2f}ms",
                extra={"event": "request_completed", "request_id": req_id},
            )
            return response
        except Exception:
            raise
        finally:
            try:
                request_id_ctx.reset(token)
            except (ValueError, RuntimeError):
                pass

    # --------------------------------------------------------------------------
    # Centralized Exception Handlers (Standard ErrorResponse Contracts)
    # --------------------------------------------------------------------------
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        req_id = getattr(request.state, "request_id", "unknown")
        logger.warning(
            f"AppException [{exc.error_code}]: {exc.message}",
            extra={"event": "app_exception", "request_id": req_id, "extra_payload": exc.details},
        )
        payload = ErrorResponse(
            error=ErrorDetail(
                code=exc.error_code,
                message=exc.message,
                request_id=req_id,
                details=exc.details,
            )
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=payload.model_dump(mode="json"),
            headers={"X-Request-ID": req_id},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        req_id = getattr(request.state, "request_id", "unknown")
        logger.warning(
            f"Request validation error: {exc.errors()}",
            extra={"event": "validation_error", "request_id": req_id},
        )
        payload = ErrorResponse(
            error=ErrorDetail(
                code="VALIDATION_ERROR",
                message="Invalid request payload or query parameters.",
                request_id=req_id,
                details={"errors": exc.errors()},
            )
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=payload.model_dump(mode="json"),
            headers={"X-Request-ID": req_id},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        req_id = getattr(request.state, "request_id", "unknown")
        code_map = {
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
        }
        error_code = code_map.get(exc.status_code, "HTTP_ERROR")
        payload = ErrorResponse(
            error=ErrorDetail(
                code=error_code,
                message=str(exc.detail),
                request_id=req_id,
                details={},
            )
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=payload.model_dump(mode="json"),
            headers={"X-Request-ID": req_id},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        req_id = getattr(request.state, "request_id", "unknown")
        logger.error(
            f"Unhandled server error: {exc!s}",
            exc_info=True,
            extra={"event": "unhandled_exception", "request_id": req_id},
        )
        payload = ErrorResponse(
            error=ErrorDetail(
                code="INTERNAL_SERVER_ERROR",
                message="An unexpected internal server error occurred. Please contact support.",
                request_id=req_id,
                details={},
            )
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=payload.model_dump(mode="json"),
            headers={"X-Request-ID": req_id},
        )

    # --------------------------------------------------------------------------
    # Mount Routers
    # --------------------------------------------------------------------------
    app.include_router(api_router)

    return app


app = create_application()
