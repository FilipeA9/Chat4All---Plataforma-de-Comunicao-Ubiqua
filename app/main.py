"""
Main FastAPI application entry point.
Initializes the application with middleware, routes, and health check endpoint.
Enhanced with OpenTelemetry distributed tracing (T019).
"""
import logging
from uuid import uuid4
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from core.config import settings
from db.database import init_db, seed_db

# OpenTelemetry imports (T019)
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

# Prometheus metrics (T102)
from prometheus_fastapi_instrumentator import Instrumentator

# Configure structured JSON logging (T020)
from core.logging_config import configure_logging
configure_logging(service_name="chat4all-api", level=settings.log_level, enable_json=True)

logger = logging.getLogger(__name__)


# Initialize OpenTelemetry Tracing (T019)
def setup_tracing():
    """
    Configure OpenTelemetry distributed tracing with Jaeger exporter.
    
    Traces are exported to Jaeger for visualization and analysis.
    Each trace includes spans for HTTP requests, database queries, and Kafka operations.
    """
    # Create resource with service information
    resource = Resource.create({
        "service.name": "chat4all-api",
        "service.version": "2.0.0",
        "deployment.environment": "production"
    })
    
    # Configure tracer provider
    tracer_provider = TracerProvider(resource=resource)
    
    # Configure Jaeger exporter
    jaeger_exporter = JaegerExporter(
        agent_host_name=settings.jaeger_host if hasattr(settings, 'jaeger_host') else "localhost",
        agent_port=int(settings.jaeger_port) if hasattr(settings, 'jaeger_port') else 6831,
    )
    
    # Add batch span processor (processes spans in batches for efficiency)
    span_processor = BatchSpanProcessor(jaeger_exporter)
    tracer_provider.add_span_processor(span_processor)
    
    # Set global tracer provider
    trace.set_tracer_provider(tracer_provider)
    
    logger.info("OpenTelemetry tracing initialized with Jaeger exporter")
    
    return tracer_provider


# Initialize tracing
tracer_provider = setup_tracing()


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
    
    # Start WebSocket heartbeat monitor and Redis subscriber
    import asyncio
    from api.websocket_manager import heartbeat_monitor, connection_manager
    from api.redis_subscriber import start_redis_subscriber, stop_redis_subscriber
    
    heartbeat_task = asyncio.create_task(heartbeat_monitor())
    logger.info("WebSocket heartbeat monitor started")
    
    await start_redis_subscriber(connection_manager)
    logger.info("Redis Pub/Sub subscriber started")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Chat4All API...")
    
    heartbeat_task.cancel()
    try:
        await heartbeat_task
    except asyncio.CancelledError:
        logger.info("Heartbeat monitor stopped")
    
    await stop_redis_subscriber()
    logger.info("Redis subscriber stopped")


# Create FastAPI application
app = FastAPI(
    title="Chat4All API Hub",
    description="API de comunicação ubíqua para integração multi-canal",
    version="2.0.0",
    lifespan=lifespan
)

# Instrument FastAPI with OpenTelemetry (T019)
FastAPIInstrumentor.instrument_app(app)

# Instrument SQLAlchemy for database query tracing (T019)
from db.database import engine
SQLAlchemyInstrumentor().instrument(engine=engine)

# Instrument FastAPI with Prometheus metrics (T102)
# Exposes /metrics endpoint with HTTP request metrics
Instrumentator().instrument(app).expose(app, endpoint="/metrics", tags=["Metrics"])

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
async def root():
    """
    Root endpoint redirect to docs.
    """
    return {
        "message": "Chat4All API - Production Ready",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health",
        "ready": "/ready"
    }


# Register endpoint routers
from api.endpoints import auth_router, conversations_router, messages_router, files_router, websocket_router
from api.auth import router as oauth_router
from api.health import router as health_router

# OAuth 2.0 Authentication (new)
app.include_router(oauth_router)

# Health Checks (new)
app.include_router(health_router)

# Legacy auth and business endpoints
app.include_router(auth_router, prefix="/auth/legacy", tags=["Authentication (Legacy)"])
app.include_router(conversations_router, prefix="/v1/conversations", tags=["Conversations"])
app.include_router(messages_router, prefix="/v1/messages", tags=["Messages"])
app.include_router(files_router, prefix="/v1/files", tags=["Files"])

# WebSocket endpoint
app.include_router(websocket_router, tags=["WebSocket"])

# Add rate limiting middleware
from api.rate_limit import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)


if __name__ == "__main__":
    import uvicorn
    import os
    import ssl
    
    # TLS 1.3 Configuration (T015)
    ssl_enabled = os.getenv("SSL_ENABLED", "false").lower() == "true"
    ssl_cert_file = os.getenv("SSL_CERT_FILE", "./certs/server.crt")
    ssl_key_file = os.getenv("SSL_KEY_FILE", "./certs/server.key")
    
    # Build uvicorn configuration
    uvicorn_config = {
        "app": "main:app",
        "host": settings.api_host,
        "port": settings.api_port,
        "reload": True,
        "log_level": settings.log_level.lower()
    }
    
    # Add TLS configuration if enabled
    if ssl_enabled:
        if os.path.exists(ssl_cert_file) and os.path.exists(ssl_key_file):
            # Create SSL context with TLS 1.3 minimum
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.minimum_version = ssl.TLSVersion.TLSv1_3
            ssl_context.load_cert_chain(ssl_cert_file, ssl_key_file)
            
            # Configure strong cipher suites (TLS 1.3)
            ssl_context.set_ciphers('TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:TLS_AES_128_GCM_SHA256')
            
            uvicorn_config["ssl_context"] = ssl_context
            logger.info(f"TLS 1.3 enabled with certificates: {ssl_cert_file}")
        else:
            logger.warning(f"SSL enabled but certificates not found. Running without TLS.")
            logger.warning(f"Expected: {ssl_cert_file} and {ssl_key_file}")
    else:
        logger.info("Running in HTTP mode (SSL_ENABLED=false)")
    
    uvicorn.run(**uvicorn_config)
