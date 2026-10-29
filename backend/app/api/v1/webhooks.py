"""Webhook endpoints for external automation engines including n8n."""

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.schemas.n8n_webhook import N8nFollowUpEventRequest, N8nFollowUpEventResponse
from app.services.n8n_followup_service import N8nFollowUpService

router = APIRouter(prefix="/webhooks", tags=["Webhooks & Automation"])


@router.post(
    "/n8n",
    response_model=N8nFollowUpEventResponse,
    status_code=status.HTTP_200_OK,
    summary="n8n Automation Relay Webhook",
    description=(
        "Authenticated webhook endpoint for n8n automation relay. Enforces backend approval "
        "rules, event idempotency, bounded retries, and records visible delivery records."
    ),
)
def handle_n8n_webhook(
    event_data: N8nFollowUpEventRequest,
    x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> N8nFollowUpEventResponse:
    # Accept secret from either X-Webhook-Secret or Authorization: Bearer <secret>
    secret = x_webhook_secret
    if not secret and authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            secret = parts[1]

    return N8nFollowUpService.process_event(
        db=db,
        event_data=event_data,
        secret_header=secret,
    )

