from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.utils.response import error_response


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except HTTPException as exc:
            raise exc
        except Exception as exc:
            return JSONResponse(
                status_code=500,
                content=error_response("Internal server error", {"detail": str(exc)}),
            )
