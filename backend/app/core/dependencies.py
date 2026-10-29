"""Dependency injection providers for FastAPI endpoints and services."""

from fastapi import Request

from app.agents.registry import AgentRegistry, get_agent_registry
from app.ai.base import LLMProvider
from app.ai.factory import get_llm_provider
from app.core.config import Settings, get_settings
from app.core.security import (
    AuthenticatedUser,
    Role,
    get_current_user,
    require_admin,
    require_agent_or_admin,
    require_role,
    require_viewer_or_above,
)
from app.crm.base import CRMProvider
from app.crm.mock import MockCRMProvider
from app.db.session import get_db
from app.integrations.whatsapp.service import WhatsAppService
from app.rag.base import Retriever
from app.rag.mock import MockRetriever
from app.tools.registry import ToolRegistry, get_tool_registry

# Shared mock CRM instance for application lifecycle
_crm_instance = MockCRMProvider()
_retriever_instance = MockRetriever()
_whatsapp_service = WhatsAppService()


def get_request_id(request: Request) -> str:
    """Retrieve the correlation request ID assigned to the request."""
    return getattr(request.state, "request_id", "unknown")


def get_app_settings() -> Settings:
    """Provide application configuration settings."""
    return get_settings()


def get_llm() -> LLMProvider:
    """Provide configured LLM provider instance."""
    return get_llm_provider()


def get_tools() -> ToolRegistry:
    """Provide ToolRegistry instance."""
    return get_tool_registry()


def get_agents() -> AgentRegistry:
    """Provide AgentRegistry instance."""
    return get_agent_registry()


def get_crm() -> CRMProvider:
    """Provide CRM provider instance."""
    return _crm_instance


def get_retriever() -> Retriever:
    """Provide RAG Retriever instance."""
    return _retriever_instance


def get_whatsapp() -> WhatsAppService:
    """Provide WhatsApp domain service."""
    return _whatsapp_service


__all__ = [
    "get_db",
    "get_request_id",
    "get_app_settings",
    "get_llm",
    "get_tools",
    "get_agents",
    "get_crm",
    "get_retriever",
    "get_whatsapp",
    "get_current_user",
    "require_role",
    "require_admin",
    "require_agent_or_admin",
    "require_viewer_or_above",
    "Role",
    "AuthenticatedUser",
]
