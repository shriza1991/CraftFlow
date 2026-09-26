"""Audit service recording immutable audit trails for critical business operations."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger, request_id_ctx
from app.db.models.audit_log import AuditLog
from app.db.models.enums import ActorType

logger = get_logger(__name__)


class AuditService:
    """Service responsible for creating append-only audit trail entries."""

    @staticmethod
    def record(
        db: Session,
        action: str,
        entity_type: str,
        entity_id: str,
        actor_type: ActorType | str = ActorType.SYSTEM,
        actor_id: str | None = None,
        description: str | None = None,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> AuditLog:
        """Create and persist an append-only audit log record."""
        req_id = request_id or request_id_ctx.get()
        actor_type_val = actor_type.value if isinstance(actor_type, ActorType) else str(actor_type)

        audit = AuditLog(
            actor_type=actor_type_val,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            request_id=req_id,
            description=description,
            before_state=before_state,
            after_state=after_state,
            metadata_=metadata or {},
            created_at=datetime.now(UTC),
        )
        db.add(audit)
        # Flush to generate ID without ending current transaction
        db.flush()

        logger.info(
            f"Audit recorded: {action} on {entity_type}:{entity_id}",
            extra={"event": "audit_record", "request_id": req_id},
        )
        return audit
