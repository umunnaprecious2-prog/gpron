"""Reject oversized request bodies before they are parsed.

Multipart bodies are parsed (and file parts buffered) before a route handler
runs, so a size check inside the handler is too late. This checks the
declared Content-Length up front. Browsers always send it for fetch() with
FormData; the route still re-checks the actual bytes it reads.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Headroom over the audio limit for multipart boundaries and form fields.
_MULTIPART_OVERHEAD = 64 * 1024
_DEFAULT_LIMIT = 64 * 1024


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, voice_limit: int):
        super().__init__(app)
        self._voice_limit = voice_limit + _MULTIPART_OVERHEAD

    def _limit_for(self, path: str) -> int:
        if path.startswith("/support/") and path.endswith("/voice"):
            return self._voice_limit
        return _DEFAULT_LIMIT if path.startswith("/support/") else 0

    async def dispatch(self, request: Request, call_next):
        limit = self._limit_for(request.url.path)
        length = request.headers.get("content-length")
        if limit and length and length.isdigit() and int(length) > limit:
            return JSONResponse(
                status_code=413, content={"detail": "Request too large."}
            )
        return await call_next(request)
