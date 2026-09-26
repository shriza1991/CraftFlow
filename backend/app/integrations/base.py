"""Base contracts for external integration clients and services."""

from abc import ABC, abstractmethod


class ExternalClient(ABC):
    """Low-level HTTP/protocol client communicating with external vendor API."""

    @abstractmethod
    async def ping(self) -> bool:
        """Verify reachability and authentication of the external service."""
        pass


class ExternalService(ABC):
    """High-level domain service providing business-oriented methods wrapping client calls."""

    @abstractmethod
    async def is_ready(self) -> bool:
        """Check if service is configured and ready for business operations."""
        pass
