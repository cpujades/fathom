from typing import Annotated

from fastapi import APIRouter, Depends

from fathom.api.deps.auth import AuthContext, get_auth_context
from fathom.application.billing import create_checkout_session
from fathom.core.config import Settings, get_settings
from fathom.schemas.billing import CheckoutSessionRequest, CheckoutSessionResponse
from fathom.schemas.errors import ErrorResponse

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post(
    "/checkout",
    response_model=CheckoutSessionResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        400: {"model": ErrorResponse, "description": "Invalid request payload."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
    },
)
async def create_checkout(
    request: CheckoutSessionRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CheckoutSessionResponse:
    return await create_checkout_session(request, auth, settings)
