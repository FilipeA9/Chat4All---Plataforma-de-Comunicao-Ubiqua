"""
Main FastAPI application entry point.
Initializes the application with middleware, routes, and health check endpoint.
"""
import logging
from uuid import uuid4
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from core.config import settings
from db.database import init_db, seed_db

# Configure logging
logging.basicConfig(
    level=settings.log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting Chat4All API...")
    try:
        init_db()
        seed_db()
        logger.info("Database initialized and seeded")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Chat4All API...")


# Create FastAPI application
app = FastAPI(
    title="Chat4All API Hub",
    description="API de comunicação ubíqua para integração multi-canal",
    version="1.0.0",
    lifespan=lifespan
)

# Request ID middleware
class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add unique request_id to each request.
    The request_id is included in logs for request tracing.
    """
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid4())
        request.state.request_id = request_id
        
        # Log incoming request with request_id
        logger.info(
            f"[{request_id}] {request.method} {request.url.path} - "
            f"Client: {request.client.host if request.client else 'unknown'}"
        )
        
        # Process request
        response = await call_next(request)
        
        # Add request_id to response headers
        response.headers["X-Request-ID"] = request_id
        
        # Log response status
        logger.info(f"[{request_id}] Response: {response.status_code}")
        
        return response


# Add middlewares
app.add_middleware(RequestIDMiddleware)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Health"])
async def health_check():
    """
    Health check endpoint.
    Returns API status and version information.
    """
    return {
        "status": "healthy",
        "service": "Chat4All API Hub",
        "version": "1.0.0"
    }


# Register endpoint routers
from api.endpoints import auth_router, conversations_router, messages_router, files_router
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(conversations_router, prefix="/v1/conversations", tags=["Conversations"])
app.include_router(messages_router, prefix="/v1/messages", tags=["Messages"])
app.include_router(files_router, prefix="/v1/files", tags=["Files"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        log_level=settings.log_level.lower()
    )
