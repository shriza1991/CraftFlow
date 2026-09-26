"""Google Workspace Domain Service."""

from typing import Any

from app.integrations.base import ExternalService
from app.integrations.google.client import GoogleWorkspaceClient


class GoogleWorkspaceService(ExternalService):
    """Domain service managing sync and exports to Google Sheets/Workspace."""

    def __init__(self, client: GoogleWorkspaceClient | None = None):
        self.client = client or GoogleWorkspaceClient(is_mock=True)

    async def is_ready(self) -> bool:
        return await self.client.ping()

    async def log_lead_to_sheet(self, spreadsheet_id: str, row_data: list[Any]) -> dict[str, Any]:
        """Append business lead metadata row to tracking sheet."""
        return await self.client.append_sheet_row(
            spreadsheet_id=spreadsheet_id,
            range_name="Leads!A:Z",
            values=row_data,
        )
