import os
import time

import socketio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from src.api.v1.endpoints import adapta, blockchain, skillswarm, socratic, teacher, webhooks
from src.core.config import settings
from src.core.logger import RequestIdMiddleware
from src.sockets import sio

# Set dummy key for local testing environment without crashing LangChain
if not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = "sk-mock-key-for-local-testing-only"

# Initialize Rate Limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["5/second"])

app = FastAPI(
    title="SocraticBridge & SkillSwarm API",
    version=settings.VERSION,
    description="Main Backend services for AdaptaLearn, Blockchain, and real-time Socratic mentoring. Secure, rate-limited, and scalable.",
    contact={
        "name": "Backend Team",
        "email": "dev@skillswarm.edu",
    },
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Custom Logging Middleware
app.add_middleware(RequestIdMiddleware)


@app.middleware("http")
async def log_execution_time(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info(f"Path: {request.url.path} completed in {process_time:.4f}s")
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled Global Exception: {exc}")
    return JSONResponse(status_code=500, content={"error": str(exc), "code": 500})


# CORS setup
# Secure CORS for Frontend App
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://skillswarm.edu",  # Prod Placeholder
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(socratic.router, prefix="/api/v1/socratic", tags=["SocraticBridge"])
app.include_router(skillswarm.router, prefix="/api/v1/skillswarm", tags=["SkillSwarm"])
app.include_router(adapta.router, prefix="/api/v1/adapta", tags=["AdaptaLearn"])
app.include_router(webhooks.router, prefix="/api/v1/webhooks", tags=["Webhooks"])
app.include_router(blockchain.router, prefix="/api/v1/blockchain", tags=["Blockchain"])
app.include_router(teacher.router, prefix="/api/v1/teacher", tags=["Teacher Dashboard"])

# Wrap the FastAPI application with the Socket.IO ASGI app handler
app_with_sockets = socketio.ASGIApp(sio, app)


@app.get("/health", tags=["System"])
async def health_check():
    """
    Health check endpoint to ensure the API is running correctly.
    """
    return {"status": "ok", "version": settings.VERSION}


@app.get("/", tags=["System"])
async def root():
    return {"message": f"Welcome to {settings.PROJECT_NAME} API"}
