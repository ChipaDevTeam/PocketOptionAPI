"""
Professional Async PocketOption API - Core module
Fully async implementation with modern Python practices
"""

from .client import AsyncPocketOptionClient
from .exceptions import (
    PocketOptionError,
    ConnectionError,
    AuthenticationError,
    OrderError,
    TimeoutError,
    InvalidParameterError,
    WebSocketError,
)
from .models import (
    Balance,
    Candle,
    Order,
    OrderResult,
    OrderStatus,
    OrderDirection,
    Asset,
    ConnectionStatus,
)
from .constants import ASSETS, Regions

# Import monitoring components
from .monitoring import (
    ErrorMonitor,
    HealthChecker,
    ErrorSeverity,
    ErrorCategory,
    CircuitBreaker,
    RetryPolicy,
    error_monitor,
    health_checker,
)

# Create REGIONS instance
REGIONS = Regions()

__version__ = "2.0.1"
__author__ = "PocketOptionAPI Team"

__all__ = [
    "AsyncPocketOptionClient",
    "PocketOptionError",
    "ConnectionError",
    "AuthenticationError",
    "OrderError",
    "TimeoutError",
    "InvalidParameterError",
    "WebSocketError",
    "Balance",
    "Candle",
    "Order",
    "OrderResult",
    "OrderStatus",
    "OrderDirection",
    "Asset",
    "ConnectionStatus",
    "ASSETS",
    "REGIONS",
    "ErrorMonitor",
    "HealthChecker",
    "ErrorSeverity",
    "ErrorCategory",
    "CircuitBreaker",
    "RetryPolicy",
    "error_monitor",
    "health_checker",
]
