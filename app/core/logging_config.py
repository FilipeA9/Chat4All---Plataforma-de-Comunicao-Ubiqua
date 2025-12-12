"""
Structured JSON logging configuration for production observability (T020).

Provides structured JSON logging with mandatory fields:
- timestamp (ISO 8601)
- level (INFO, WARNING, ERROR, etc.)
- service (service name)
- trace_id (OpenTelemetry trace ID for correlation)
- request_id (unique per-request identifier)
- message (log message)

Usage:
    from core.logging_config import get_logger
    
    logger = get_logger(__name__)
    logger.info("User authenticated", extra={"user_id": 123, "username": "user1"})
"""
import logging
import json
import sys
from datetime import datetime
from typing import Dict, Any, Optional
from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """
    Custom JSON formatter with mandatory observability fields.
    
    Ensures all log records include:
    - timestamp: ISO 8601 timestamp
    - level: Log level (INFO, WARNING, ERROR, etc.)
    - service: Service name (e.g., "chat4all-api", "chat4all-worker")
    - trace_id: OpenTelemetry trace ID (if available)
    - request_id: Per-request correlation ID (if available)
    - message: Log message
    - Additional context from 'extra' parameter
    """
    
    def __init__(self, service_name: str = "chat4all", *args, **kwargs):
        """
        Initialize JSON formatter.
        
        Args:
            service_name: Name of the service emitting logs
        """
        self.service_name = service_name
        super().__init__(*args, **kwargs)
    
    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, message_dict: Dict[str, Any]) -> None:
        """
        Add mandatory fields to log record.
        
        Args:
            log_record: Dictionary to be JSON-serialized
            record: Python logging.LogRecord
            message_dict: Message dictionary
        """
        super().add_fields(log_record, record, message_dict)
        
        # Mandatory fields (T020)
        log_record['timestamp'] = datetime.utcnow().isoformat() + 'Z'
        log_record['level'] = record.levelname
        log_record['service'] = self.service_name
        log_record['message'] = record.getMessage()
        
        # Add trace_id if available (from OpenTelemetry context)
        if hasattr(record, 'trace_id'):
            log_record['trace_id'] = record.trace_id
        
        # Add request_id if available (from FastAPI request state)
        if hasattr(record, 'request_id'):
            log_record['request_id'] = record.request_id
        
        # Add exception info if present
        if record.exc_info:
            log_record['exception'] = self.formatException(record.exc_info)
        
        # Add module and function name for debugging
        log_record['module'] = record.module
        log_record['function'] = record.funcName
        log_record['line'] = record.lineno


def configure_logging(
    service_name: str = "chat4all",
    level: str = "INFO",
    enable_json: bool = True
) -> None:
    """
    Configure structured JSON logging for the application.
    
    Args:
        service_name: Name of the service (e.g., "chat4all-api", "chat4all-worker")
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        enable_json: Whether to use JSON formatting (True for production)
    
    Example:
        configure_logging(service_name="chat4all-api", level="INFO", enable_json=True)
    """
    # Convert level string to logging constant
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers
    root_logger.handlers = []
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    if enable_json:
        # Use JSON formatter for production (T020)
        formatter = CustomJsonFormatter(
            service_name=service_name,
            fmt='%(timestamp)s %(level)s %(service)s %(trace_id)s %(request_id)s %(message)s'
        )
    else:
        # Use standard formatter for development
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Suppress noisy third-party loggers
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('kafka').setLevel(logging.WARNING)
    logging.getLogger('aiokafka').setLevel(logging.WARNING)
    

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with proper configuration.
    
    Args:
        name: Logger name (typically __name__ of the module)
    
    Returns:
        Configured logger instance
    
    Example:
        logger = get_logger(__name__)
        logger.info("User action", extra={"user_id": 123, "action": "login"})
    """
    return logging.getLogger(name)


class LogContextFilter(logging.Filter):
    """
    Logging filter to inject trace_id and request_id into log records.
    
    Extracts trace_id from OpenTelemetry context and request_id from
    application context (e.g., FastAPI request state).
    """
    
    def filter(self, record: logging.LogRecord) -> bool:
        """
        Add trace_id and request_id to log record if available.
        
        Args:
            record: Log record to augment
        
        Returns:
            True (always allow record through)
        """
        # Try to get trace_id from OpenTelemetry context
        try:
            from opentelemetry import trace
            span = trace.get_current_span()
            if span:
                span_context = span.get_span_context()
                if span_context.is_valid:
                    record.trace_id = format(span_context.trace_id, '032x')
                else:
                    record.trace_id = 'no-trace'
            else:
                record.trace_id = 'no-trace'
        except Exception:
            record.trace_id = 'no-trace'
        
        # Try to get request_id from application context
        # Note: This will be set by middleware/dependency injection
        if not hasattr(record, 'request_id'):
            record.request_id = 'no-request'
        
        return True


# Add context filter to root logger
context_filter = LogContextFilter()
logging.getLogger().addFilter(context_filter)
