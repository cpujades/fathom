from __future__ import annotations

from stripe import StripeClient

from fathom.core.config import Settings
from fathom.core.errors import ConfigurationError


def create_stripe_client(settings: Settings) -> StripeClient:
    if not settings.stripe_secret_key:
        raise ConfigurationError("STRIPE_SECRET_KEY is not configured.")
    return StripeClient(settings.stripe_secret_key)


def get_stripe_webhook_secret(settings: Settings) -> str:
    if not settings.stripe_webhook_secret:
        raise ConfigurationError("STRIPE_WEBHOOK_SECRET is not configured.")
    return settings.stripe_webhook_secret


def get_stripe_success_url(settings: Settings) -> str:
    if not settings.stripe_success_url:
        raise ConfigurationError("STRIPE_SUCCESS_URL is not configured.")
    return settings.stripe_success_url


def get_stripe_cancel_url(settings: Settings) -> str:
    if not settings.stripe_cancel_url:
        raise ConfigurationError("STRIPE_CANCEL_URL is not configured.")
    return settings.stripe_cancel_url
