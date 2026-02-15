from typing import Annotated

from fastapi import APIRouter, Depends, Request

from fathom.application.billing import handle_polar_webhook
from fathom.core.config import Settings, get_settings
from fathom.schemas.errors import ErrorResponse

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post(
    "/polar",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid webhook payload or signature."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
    },
)
async def polar_webhook(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    payload = await request.body()
    await handle_polar_webhook(payload, request.headers, settings)
    return {"status": "ok"}
