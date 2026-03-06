import sys
import uuid

from fastapi import Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

# Configure loguru
logger.remove()
logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level> | {extra}",
    enqueue=True,  # Thread-safe logging
)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware that generates a unique UUID for each incoming request
    and binds it to the loguru context.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())

        # Attach to the request state so it's accessible in route handlers
        request.state.request_id = request_id

        # Bind the request_id context to loguru for all subsequent logs in this async context
        with logger.contextualize(request_id=request_id):
            response = await call_next(request)

            # Inject the request ID into the response headers for the client
            response.headers["X-Request-ID"] = request_id
            return response
