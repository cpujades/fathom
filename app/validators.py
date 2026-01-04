from app.core.constants import SUMMARY_ID_RE
from app.core.errors import InvalidRequestError


def validate_summary_id(summary_id: str) -> None:
    if not SUMMARY_ID_RE.match(summary_id):
        raise InvalidRequestError("Invalid summary id")
