"""Google Workspace API client boundary."""

from typing import Any

from app.integrations.base import ExternalClient


class GoogleWorkspaceClient(ExternalClient):
    """Client for interacting with Google Sheets, Drive, and Workspace APIs."""

    def __init__(self, service_account_info: dict[str, Any] | None = None, is_mock: bool = True):
        self.service_account_info = service_account_info
        self.is_mock = is_mock

    async def ping(self) -> bool:
        return True

    async def append_sheet_row(
        self, spreadsheet_id: str, range_name: str, values: list[Any]
    ) -> dict[str, Any]:
        """Append a row of data to a Google Sheet."""
        if self.is_mock:
            return {
                "spreadsheetId": spreadsheet_id,
                "tableRange": range_name,
                "updates": {"updatedRows": 1, "updatedColumns": len(values)},
            }
        return {"status": "mock_mode"}
