from typing import Annotated

from fastapi import APIRouter, Depends, Request

from fathom.application.billing import handle_stripe_webhook
from fathom.core.config import Settings, get_settings
from fathom.schemas.errors import ErrorResponse

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post(
    "/stripe",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid webhook payload or signature."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
    },
)
async def stripe_webhook(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    payload = await request.body()
    signature = request.headers.get("Stripe-Signature")
    await handle_stripe_webhook(payload, signature, settings)
    return {"status": "ok"}
