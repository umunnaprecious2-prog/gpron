import logging
import os

from google.auth.transport import requests
from google.oauth2 import id_token

from app.config import settings
from app.exceptions.errors import UnauthorizedError

logger = logging.getLogger(__name__)

# OAUTHLIB_INSECURE_TRANSPORT affects oauthlib's HTTP-transport check, not
# clock-skew verification below; kept for parity with prior behavior but set
# once at import time instead of on every request. setdefault() so it never
# overrides a value the real environment already set.
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "true")


async def verify_google_token(token: str) -> dict:
    """
    Verify Google ID token and return user info.
    Returns: {id, email, name, picture}
    """
    try:
        idinfo = id_token.verify_oauth2_token(
            token,
            requests.Request(),
            settings.google_client_id,
            clock_skew_in_seconds=60,  # small allowance for clock drift
        )

        if idinfo.get("aud") != settings.google_client_id:
            raise ValueError("Token audience mismatch")

        return {
            "id": idinfo.get("sub"),
            "email": idinfo.get("email"),
            "name": idinfo.get("name"),
            "picture": idinfo.get("picture"),
        }
    except Exception as e:
        # Don't echo the raw exception to the client, it can leak internal
        # library/network detail. Log it server-side instead.
        logger.warning("Google token verification failed: %s", e)
        raise UnauthorizedError("Invalid Google token")
