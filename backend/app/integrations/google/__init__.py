"""Google Workspace Integration package."""

from app.integrations.google.client import GoogleWorkspaceClient
from app.integrations.google.service import GoogleWorkspaceService

__all__ = ["GoogleWorkspaceClient", "GoogleWorkspaceService"]
