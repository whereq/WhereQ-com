"""Error envelope + request-id plumbing for the Maps service (spec §5).

Every response carries ``X-Request-Id``; error responses mirror it in the JSON
body as ``error.request_id``.
"""

from __future__ import annotations

import uuid

from fastapi import Request
from fastapi.responses import JSONResponse


class MapsError(Exception):
    """A Maps-service error that renders as the §5 envelope."""

    def __init__(self, status_code: int, code: str, message: str,
                 *, retry_after: int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retry_after = retry_after


def new_request_id() -> str:
    return "wqm_" + uuid.uuid4().hex


def request_id_of(request: Request) -> str:
    return getattr(request.state, "request_id", None) or new_request_id()


def error_json(status_code: int, code: str, message: str, request_id: str,
               *, retry_after: int | None = None) -> JSONResponse:
    headers = {"X-Request-Id": request_id}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
        headers=headers,
    )


async def maps_error_handler(request: Request, exc: MapsError) -> JSONResponse:
    return error_json(exc.status_code, exc.code, exc.message,
                      request_id_of(request), retry_after=exc.retry_after)
