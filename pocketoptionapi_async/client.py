"""
Professional Async PocketOption API Client
"""

import asyncio
import json
import time
import uuid
from typing import Optional, List, Dict, Any, Union, Callable
from datetime import datetime, timedelta
from collections import defaultdict
import pandas as pd
from loguru import logger

from .monitoring import error_monitor, health_checker, ErrorCategory, ErrorSeverity
from .websocket_client import AsyncWebSocketClient
from .models import (
    Balance,
    Candle,
    Order,
    OrderResult,
    OrderStatus,
    OrderDirection,
    ServerTime,
)
from .constants import ASSETS, REGIONS, TIMEFRAMES, API_LIMITS
from .exceptions import (
    PocketOptionError,
    ConnectionError,
    AuthenticationError,
    OrderError,
    InvalidParameterError,
)


class AsyncPocketOptionClient:
    """
    Professional async PocketOption API client with modern Python practices
    """

    def __init__(
        self,
        ssid: str,
        is_demo: bool = True,
        region: Optional[str] = None,
        uid: int = 0,
        platform: int = 1,
        is_fast_history: bool = True,
        persistent_connection: bool = False,
        auto_reconnect: bool = True,
        enable_logging: bool = True,
    ):
        """
        Initialize async PocketOption client with enhanced monitoring

        Args:
            ssid: Complete SSID string or raw session ID for authentication
            is_demo: Whether to use demo account
            region: Preferred region for connection
            uid: User ID (if providing raw session)
            platform: Platform identifier (1=web, 3=mobile)
            is_fast_history: Enable fast history loading
            persistent_connection: Enable persistent connection with keep-alive (like old API)
            auto_reconnect: Enable automatic reconnection on disconnection
            enable_logging: Enable detailed logging (default: True)
        """
        self.raw_ssid = ssid
        self.is_demo = is_demo
        self.preferred_region = region
        self.uid = uid
        self.platform = platform
        self.is_fast_history = is_fast_history
        self.persistent_connection = persistent_connection
        self.auto_reconnect = auto_reconnect
        self.enable_logging = enable_logging

        # Configure logging based on preference
        if not enable_logging:
            logger.remove()
            logger.add(lambda msg: None, level="CRITICAL")  # Disable most logging
        
        # Validate and parse SSID
        self._original_demo = None  # Store original demo value from SSID
        self._validate_and_parse_ssid(ssid)

        # Core components
        self._websocket = AsyncWebSocketClient()
        self._balance: Optional[Balance] = None
        self._orders: Dict[str, OrderResult] = {}
        self._active_orders: Dict[str, OrderResult] = {}
        self._order_results: Dict[str, OrderResult] = {}
        self._server_id_to_request_id: Dict[str, str] = {}  # Maps server deal IDs to client request IDs
        self._candles_cache: Dict[str, List[Candle]] = {}
        self._server_time: Optional[ServerTime] = None
        self._event_callbacks: Dict[str, List[Callable]] = defaultdict(list)
        # Setup event handlers for websocket messages
        self._setup_event_handlers()

        # Add handler for JSON data messages (contains detailed order data)
        self._websocket.add_event_handler("json_data", self._on_json_data)
        # Enhanced monitoring and error handling

        self._error_monitor = error_monitor
        self._health_checker = health_checker

        # Performance tracking
        self._operation_metrics: Dict[str, List[float]] = defaultdict(list)
        self._last_health_check = time.time()

        # Keep-alive functionality (based on old API patterns)
        self._keep_alive_manager = None
        self._ping_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._is_persistent = False

        # Connection statistics (like old API)
        self._connection_stats = {
            "total_connections": 0,
            "successful_connections": 0,
            "total_reconnects": 0,
            "last_ping_time": None,
            "messages_sent": 0,
            "messages_received": 0,
            "connection_start_time": None,
        }

        logger.info(
            f"Initialized PocketOption client (demo={is_demo}, uid={self.uid}, persistent={persistent_connection}) with enhanced monitoring"
            if enable_logging
            else ""
        )

    def _setup_event_handlers(self):
        """Setup WebSocket event handlers"""
        self._websocket.add_event_handler("authenticated", self._on_authenticated)
        self._websocket.add_event_handler("balance_updated", self._on_balance_updated)
        self._websocket.add_event_handler(
            "balance_data", self._on_balance_data
        )  # Add balance_data handler
        self._websocket.add_event_handler("order_opened", self._on_order_opened)
        self._websocket.add_event_handler("order_closed", self._on_order_closed)
        self._websocket.add_event_handler("stream_update", self._on_stream_update)
        self._websocket.add_event_handler("candles_received", self._on_candles_received)
        self._websocket.add_event_handler("disconnected", self._on_disconnected)

    async def connect(
        self, regions: Optional[List[str]] = None, persistent: Optional[bool] = None
    ) -> bool:
        """
        Connect to PocketOption with multiple region support

        Args:
            regions: List of regions to try (uses defaults if None)
            persistent: Override persistent connection setting

        Returns:
            bool: True if connected successfully
        """
        logger.info("Connecting to PocketOption...")
        # Update persistent setting if provided
        if persistent is not None:
            self.persistent_connection = bool(persistent)

        try:
            if self.persistent_connection:
                return await self._start_persistent_connection(regions)
            else:
                return await self._start_regular_connection(regions)

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            await self._error_monitor.record_error(
                error_type="connection_failed",
                severity=ErrorSeverity.HIGH,
                category=ErrorCategory.CONNECTION,
                message=f"Connection failed: {e}",
            )
            return False

    async def _start_regular_connection(
        self, regions: Optional[List[str]] = None
    ) -> bool:
        """Start regular connection (existing behavior)"""
        logger.info("Starting regular connection...")
        # Use appropriate regions based on demo mode
        if not regions:
            if self.is_demo:
                # For demo mode, only use demo regions
                demo_urls = REGIONS.get_demo_regions()
                regions = []
                all_regions = REGIONS.get_all_regions()
                for name, url in all_regions.items():
                    if url in demo_urls:
                        regions.append(name)
                logger.info(f"Demo mode: Using demo regions: {regions}")
            else:
                # For live mode, use all regions except demo
                all_regions = REGIONS.get_all_regions()
                regions = [
                    name
                    for name, url in all_regions.items()
                    if "DEMO" not in name.upper()
                ]
                logger.info(f"Live mode: Using non-demo regions: {regions}")
        # Update connection stats
        self._connection_stats["total_connections"] += 1
        self._connection_stats["connection_start_time"] = time.time()

        for region in regions:
            try:
                region_url = REGIONS.get_region(region)
                if not region_url:
                    continue

                urls = [region_url]  # Convert single URL to list
                logger.info(f"Trying region: {region} with URL: {region_url}")

                # Try to connect
                ssid_message = self._format_session_message()
                success = await self._websocket.connect(urls, ssid_message)

                if success:
                    logger.info(f" Connected to region: {region}")

                    # Wait for authentication
                    await self._wait_for_authentication()

                    # Initialize data
                    await self._initialize_data()

                    # Start keep-alive tasks
                    await self._start_keep_alive_tasks()

                    self._connection_stats["successful_connections"] += 1
                    logger.info("Successfully connected and authenticated")
                    return True

            except Exception as e:
                logger.warning(f"Failed to connect to region {region}: {e}")
                continue

        return False

    async def _start_persistent_connection(
        self, regions: Optional[List[str]] = None
    ) -> bool:
        """Start persistent connection with keep-alive (like old API)"""
        logger.info("Starting persistent connection with automatic keep-alive...")

        # Import the keep-alive manager
        from .connection_keep_alive import ConnectionKeepAlive

        # Create keep-alive manager
        complete_ssid = self.raw_ssid
        self._keep_alive_manager = ConnectionKeepAlive(complete_ssid, self.is_demo)

        # Add event handlers
        self._keep_alive_manager.add_event_handler(
            "connected", self._on_keep_alive_connected
        )
        self._keep_alive_manager.add_event_handler(
            "reconnected", self._on_keep_alive_reconnected
        )
        self._keep_alive_manager.add_event_handler(
            "message_received", self._on_keep_alive_message
        )

        # Add handlers for forwarded WebSocket events
        self._keep_alive_manager.add_event_handler(
            "balance_data", self._on_balance_data
        )
        self._keep_alive_manager.add_event_handler(
            "balance_updated", self._on_balance_updated
        )
        self._keep_alive_manager.add_event_handler(
            "authenticated", self._on_authenticated
        )
        self._keep_alive_manager.add_event_handler(
            "order_opened", self._on_order_opened
        )
        self._keep_alive_manager.add_event_handler(
            "order_closed", self._on_order_closed
        )
        self._keep_alive_manager.add_event_handler(
            "stream_update", self._on_stream_update
        )
        self._keep_alive_manager.add_event_handler("json_data", self._on_json_data)

        # Connect with keep-alive
        success = await self._keep_alive_manager.connect_with_keep_alive(regions)

        if success:
            self._is_persistent = True
            logger.info(" Persistent connection established successfully")
            return True
        else:
            logger.error("Failed to establish persistent connection")
            return False

    async def _start_keep_alive_tasks(self):
        """Start keep-alive tasks for regular connection"""
        logger.info("Starting keep-alive tasks for regular connection...")

        # Start ping task (like old API)
        self._ping_task = asyncio.create_task(self._ping_loop())

        # Start reconnection monitor if auto_reconnect is enabled
        if self.auto_reconnect:
            self._reconnect_task = asyncio.create_task(self._reconnection_monitor())

    async def _ping_loop(self):
        """Ping loop for regular connections (like old API)"""
        while self.is_connected and not self._is_persistent:
            try:
                await self._websocket.send_message('42["ps"]')
                self._connection_stats["last_ping_time"] = time.time()
                await asyncio.sleep(20)  # Ping every 20 seconds
            except Exception as e:
                logger.warning(f"Ping failed: {e}")
                break

    async def _reconnection_monitor(self):
        """Monitor and handle reconnections for regular connections"""
        while self.auto_reconnect and not self._is_persistent:
            await asyncio.sleep(30)  # Check every 30 seconds

            if not self.is_connected:
                logger.info("Connection lost, attempting reconnection...")
                self._connection_stats["total_reconnects"] += 1

                try:
                    success = await self._start_regular_connection()
                    if success:
                        logger.info(" Reconnection successful")
                    else:
                        logger.error("Reconnection failed")
                        await asyncio.sleep(10)  # Wait before next attempt
                except Exception as e:
                    logger.error(f"Reconnection error: {e}")
                    await asyncio.sleep(10)

    async def disconnect(self) -> None:
        """Disconnect from PocketOption and cleanup all resources"""
        logger.info("Disconnecting from PocketOption...")

        # Cancel tasks
        if self._ping_task:
            self._ping_task.cancel()
        if self._reconnect_task:
            self._reconnect_task.cancel()

        # Disconnect based on connection type
        if self._is_persistent and self._keep_alive_manager:
            await self._keep_alive_manager.disconnect()
        else:
            await self._websocket.disconnect()

        # Reset state
        self._is_persistent = False
        self._balance = None
        self._orders.clear()

        logger.info("Disconnected successfully")

    async def get_balance(self) -> Balance:
        """
        Get current account balance

        Returns:
            Balance: Current balance information
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to PocketOption")

        # Request balance update if needed
        if (
            not self._balance
            or (datetime.now() - self._balance.last_updated).seconds > 60
        ):
            await self._request_balance_update()

            # Wait a bit for balance to be received
            await asyncio.sleep(1)

        if not self._balance:
            raise PocketOptionError("Balance data not available")

        return self._balance

    async def place_order(
        self, asset: str, amount: float, direction: OrderDirection, duration: int
    ) -> OrderResult:
        """
        Place a binary options order

        Args:
            asset: Asset symbol (e.g., "EURUSD_otc")
            amount: Order amount
            direction: OrderDirection.CALL or OrderDirection.PUT
            duration: Duration in seconds

        Returns:
            OrderResult: Order placement result
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to PocketOption")
            # Validate parameters
        self._validate_order_parameters(asset, amount, direction, duration)

        try:
            # Create order
            order_id = str(uuid.uuid4())
            order = Order(
                asset=asset,
                amount=amount,
                direction=direction,
                duration=duration,
                request_id=order_id,  # Use request_id, not order_id
            )  # Send order
            await self._send_order(order)

            # Wait for result (this will either get the real server response or create a fallback)
            result = await self._wait_for_order_result(order_id, order)

            # Don't store again - _wait_for_order_result already handles storage
            logger.info(f"Order placed: {result.order_id} - {result.status}")
            return result

        except Exception as e:
            logger.error(f"Order placement failed: {e}")
            raise OrderError(f"Failed to place order: {e}")

    async def get_candles(
        self,
        asset: str,
        timeframe: Union[str, int],
        count: int = 100,
        end_time: Optional[datetime] = None,
    ) -> List[Candle]:
        """
        Get historical candle data with automatic reconnection

        Args:
            asset: Asset symbol
            timeframe: Timeframe (e.g., "1m", "5m", 60)
            count: Number of candles to retrieve
            end_time: End time for data (defaults to now)

        Returns:
            List[Candle]: Historical candle data
        """
        # Check connection and attempt reconnection if needed
        if not self.is_connected:
            if self.auto_reconnect:
                logger.info(
                    f"Connection lost, attempting reconnection for {asset} candles..."
                )
                reconnected = await self._attempt_reconnection()
                if not reconnected:
                    raise ConnectionError(
                        "Not connected to PocketOption and reconnection failed"
                    )
            else:
                raise ConnectionError("Not connected to PocketOption")

        # Convert timeframe to seconds
        if isinstance(timeframe, str):
            timeframe_seconds = TIMEFRAMES.get(timeframe, 60)
        else:
            timeframe_seconds = timeframe

        # Validate asset
        if asset not in ASSETS:
            raise InvalidParameterError(f"Invalid asset: {asset}")

        # Set default end time
        if not end_time:
            end_time = datetime.now()

        max_retries = 2
        for attempt in range(max_retries):
            try:
                # Request candle data
                candles = await self._request_candles(
                    asset, timeframe_seconds, count, end_time
                )

                # Cache results
                cache_key = f"{asset}_{timeframe_seconds}"
                self._candles_cache[cache_key] = candles

                logger.info(f"Retrieved {len(candles)} candles for {asset}")
                return candles

            except Exception as e:
                if "WebSocket is not connected" in str(e) and attempt < max_retries - 1:
                    logger.warning(
                        f"Connection lost during candle request for {asset}, attempting reconnection..."
                    )
                    if self.auto_reconnect:
                        reconnected = await self._attempt_reconnection()
                        if reconnected:
                            logger.info(
                                f" Reconnected, retrying candle request for {asset}"
                            )
                            continue

                logger.error(f"Failed to get candles for {asset}: {e}")
                raise PocketOptionError(f"Failed to get candles: {e}")

        raise PocketOptionError(f"Failed to get candles after {max_retries} attempts")

    async def get_candles_dataframe(
        self,
        asset: str,
        timeframe: Union[str, int],
        count: int = 100,
        end_time: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Get historical candle data as DataFrame

        Args:
            asset: Asset symbol
            timeframe: Timeframe (e.g., "1m", "5m", 60)
            count: Number of candles to retrieve
            end_time: End time for data (defaults to now)

        Returns:
            pd.DataFrame: Historical candle data
        """
        candles = await self.get_candles(asset, timeframe, count, end_time)

        # Convert to DataFrame
        data = []
        for candle in candles:
            data.append(
                {
                    "timestamp": candle.timestamp,
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                }
            )
        df = pd.DataFrame(data)

        if not df.empty:
            df.set_index("timestamp", inplace=True)
            df.sort_index(inplace=True)

        return df

    async def check_order_result(self, order_id: str) -> Optional[OrderResult]:
        """
        Check the result of a specific order

        Args:
            order_id: Order ID to check

        Returns:
            OrderResult: Order result or None if not found
        """
        # First check completed orders (prioritize final results over active orders)
        if order_id in self._order_results:
            return self._order_results[order_id]

        # Then check active orders
        if order_id in self._active_orders:
            return self._active_orders[order_id]

        # Not found
        return None

    async def get_active_orders(self) -> List[OrderResult]:
        """
        Get all active orders

        Returns:
            List[OrderResult]: Active orders
        """
        return list(self._active_orders.values())

    def add_event_callback(self, event: str, callback: Callable) -> None:
        """
        Add event callback

        Args:
            event: Event name (e.g., 'order_closed', 'balance_updated')
            callback: Callback function
        """
        if event not in self._event_callbacks:
            self._event_callbacks[event] = []
        self._event_callbacks[event].append(callback)

    def remove_event_callback(self, event: str, callback: Callable) -> None:
        """
        Remove event callback

        Args:
            event: Event name
            callback: Callback function to remove
        """
        if event in self._event_callbacks:
            try:
                self._event_callbacks[event].remove(callback)
            except ValueError:
                pass

    @property
    def is_connected(self) -> bool:
        """Check if client is connected (including persistent connections)"""
        if self._is_persistent and self._keep_alive_manager:
            return self._keep_alive_manager.is_connected
        else:
            return self._websocket.is_connected

    @property
    def connection_info(self):
        """Get connection information (including persistent connections)"""
        if self._is_persistent and self._keep_alive_manager:
            return self._keep_alive_manager.connection_info
        else:
            return self._websocket.connection_info

    async def send_message(self, message: str) -> bool:
        """Send message through active connection"""
        try:
            if self._is_persistent and self._keep_alive_manager:
                return await self._keep_alive_manager.send_message(message)
            else:
                await self._websocket.send_message(message)
                return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False

    def get_connection_stats(self) -> Dict[str, Any]:
        """Get comprehensive connection statistics"""
        stats = self._connection_stats.copy()

        if self._is_persistent and self._keep_alive_manager:
            stats.update(self._keep_alive_manager.get_stats())
        else:
            stats.update(
                {
                    "websocket_connected": self._websocket.is_connected,
                    "connection_info": self._websocket.connection_info,
                }
            )

        return stats  # Private methods

    def _validate_and_parse_ssid(self, ssid: str) -> None:
        """Validate and parse SSID format"""
        if not ssid or not isinstance(ssid, str):
            raise InvalidParameterError(
                "SSID must be a non-empty string. "
                "Expected format: 42[\"auth\",{\"session\":\"...\",\"isDemo\":1,\"uid\":0,\"platform\":1}]"
            )
        
        ssid = ssid.strip()
        
        # Check if it's a complete SSID format
        if ssid.startswith('42["auth",'):
            self._parse_complete_ssid(ssid)
            # Validate that we got a session ID
            if not self.session_id or len(self.session_id) < 10:
                raise InvalidParameterError(
                    f"Invalid SSID format - session ID is too short or missing. "
                    f"Please ensure your SSID is in the correct format: "
                    f"42[\"auth\",{{\"session\":\"your_session_id\",\"isDemo\":1,\"uid\":12345,\"platform\":1}}]. "
                    f"You can get this from browser DevTools (F12) -> Network tab -> WS filter -> "
                    f"look for authentication message starting with 42[\"auth\","
                )
        else:
            # Treat as raw session ID
            if len(ssid) < 10:
                logger.warning(
                    f"Raw session ID appears to be too short ({len(ssid)} chars). "
                    f"If you're having connection issues, please use the complete SSID format: "
                    f"42[\"auth\",{{\"session\":\"your_session\",\"isDemo\":1,\"uid\":12345,\"platform\":1}}]"
                )
            self.session_id = ssid
            self._complete_ssid = None

    def _format_session_message(self) -> str:
        """Format session authentication message"""
        # Always create auth message from components using constructor parameters
        # This ensures is_demo parameter is respected regardless of SSID format
        auth_data = {
            "session": self.session_id,
            "isDemo": 1 if self.is_demo else 0,
            "uid": self.uid,
            "platform": self.platform,
        }

        if self.is_fast_history:
            auth_data["isFastHistory"] = True

        return f'42["auth",{json.dumps(auth_data)}]'

    def _parse_complete_ssid(self, ssid: str) -> None:
        """Parse complete SSID auth message to extract components"""
        try:
            # Extract JSON part
            json_start = ssid.find("{")
            json_end = ssid.rfind("}") + 1
            if json_start != -1 and json_end > json_start:
                json_part = ssid[json_start:json_end]
                data = json.loads(json_part)

                self.session_id = data.get("session", "")
                if not self.session_id:
                    raise InvalidParameterError(
                        "SSID is missing the 'session' field. "
                        "Expected format: 42[\"auth\",{\"session\":\"your_session\",\"isDemo\":1,\"uid\":12345,\"platform\":1}]"
                    )
                
                # Store original demo value from SSID, but don't override the constructor parameter
                self._original_demo = bool(data.get("isDemo", 1))
                # Keep the is_demo value from constructor - don't override it
                self.uid = data.get("uid", 0)
                self.platform = data.get("platform", 1)
                # Don't store complete SSID - we'll reconstruct it with correct demo value
                self._complete_ssid = None
            else:
                raise InvalidParameterError(
                    "Could not parse SSID - JSON object not found. "
                    "Expected format: 42[\"auth\",{\"session\":\"your_session\",\"isDemo\":1,\"uid\":12345,\"platform\":1}]"
                )
        except json.JSONDecodeError as e:
            raise InvalidParameterError(
                f"Invalid SSID format - JSON parsing failed: {e}. "
                f"Expected format: 42[\"auth\",{{\"session\":\"your_session\",\"isDemo\":1,\"uid\":12345,\"platform\":1}}]"
            )
        except InvalidParameterError:
            raise  # Re-raise our custom errors
        except Exception as e:
            raise InvalidParameterError(
                f"Failed to parse SSID: {e}. "
                f"Expected format: 42[\"auth\",{{\"session\":\"your_session\",\"isDemo\":1,\"uid\":12345,\"platform\":1}}]"
            )

    async def _wait_for_authentication(self, timeout: float = 10.0) -> None:
        """Wait for authentication to complete (like old API)"""
        auth_received = False
        auth_error = None

        def on_auth(data):
            nonlocal auth_received
            auth_received = True
        
        def on_auth_error(data):
            nonlocal auth_error
            auth_error = data.get("message", "Unknown authentication error")

        # Add temporary handlers
        self._websocket.add_event_handler("authenticated", on_auth)
        self._websocket.add_event_handler("auth_error", on_auth_error)

        try:
            # Wait for authentication
            start_time = time.time()
            while not auth_received and not auth_error and (time.time() - start_time) < timeout:
                await asyncio.sleep(0.1)

            if auth_error:
                raise AuthenticationError(
                    f"Authentication failed: {auth_error}. "
                    f"Please verify your SSID is correct. "
                    f"SSID should be in format: 42[\"auth\",{{\"session\":\"your_session\",\"isDemo\":1,\"uid\":12345,\"platform\":1}}]. "
                    f"Get it from browser DevTools (F12) -> Network tab -> WS filter -> look for message starting with 42[\"auth\","
                )
            
            if not auth_received:
                raise AuthenticationError(
                    "Authentication timeout - server did not respond to authentication request. "
                    "This usually means your SSID is invalid or expired. "
                    "Please get a fresh SSID from browser DevTools (F12) -> Network tab -> WS filter -> "
                    "look for authentication message starting with 42[\"auth\",{\"session\":\"...\",..."
                )

        finally:
            # Remove temporary handlers
            self._websocket.remove_event_handler("authenticated", on_auth)
            self._websocket.remove_event_handler("auth_error", on_auth_error)

    async def _initialize_data(self) -> None:
        """Initialize client data after connection"""
        # Request initial balance
        await self._request_balance_update()

        # Setup time synchronization
        await self._setup_time_sync()

    async def _request_balance_update(self) -> None:
        """Request balance update from server"""
        message = '42["getBalance"]'

        # Use appropriate connection method
        if self._is_persistent and self._keep_alive_manager:
            await self._keep_alive_manager.send_message(message)
        else:
            await self._websocket.send_message(message)

    async def _setup_time_sync(self) -> None:
        """Setup server time synchronization"""
        # This would typically involve getting server timestamp
        # For now, create a basic time sync object
        local_time = datetime.now().timestamp()
        self._server_time = ServerTime(
            server_timestamp=local_time, local_timestamp=local_time, offset=0.0
        )

    def _validate_order_parameters(
        self, asset: str, amount: float, direction: OrderDirection, duration: int
    ) -> None:
        """Validate order parameters"""
        if asset not in ASSETS:
            raise InvalidParameterError(f"Invalid asset: {asset}")

        if (
            amount < API_LIMITS["min_order_amount"]
            or amount > API_LIMITS["max_order_amount"]
        ):
            raise InvalidParameterError(
                f"Amount must be between {API_LIMITS['min_order_amount']} and {API_LIMITS['max_order_amount']}"
            )

        if (
            duration < API_LIMITS["min_duration"]
            or duration > API_LIMITS["max_duration"]
        ):
            raise InvalidParameterError(
                f"Duration must be between {API_LIMITS['min_duration']} and {API_LIMITS['max_duration']} seconds"
            )

    async def _send_order(self, order: Order) -> None:
        """Send order to server"""
        # Format asset name with # prefix if not already present
        asset_name = order.asset

        # Create the message in the correct PocketOption format
        message = f'42["openOrder",{{"asset":"{asset_name}","amount":{order.amount},"action":"{order.direction.value}","isDemo":{1 if self.is_demo else 0},"requestId":"{order.request_id}","optionType":100,"time":{order.duration}}}]'

        # Send using appropriate connection
        if self._is_persistent and self._keep_alive_manager:
            await self._keep_alive_manager.send_message(message)
        else:
            await self._websocket.send_message(message)

        if self.enable_logging:
            logger.debug(f"Sent order: {message}")

    async def _wait_for_order_result(
        self, request_id: str, order: Order, timeout: float = 30.0
    ) -> OrderResult:
        """Wait for order execution result"""
        start_time = time.time()

        # Wait for order to appear in tracking system
        while time.time() - start_time < timeout:
            # Check if order was added to active orders (by _on_order_opened or _on_json_data)
            if request_id in self._active_orders:
                if self.enable_logging:
                    logger.success(f" Order {request_id} found in active tracking")
                return self._active_orders[request_id]

            # Check if order went directly to results (failed or completed)
            if request_id in self._order_results:
                if self.enable_logging:
                    logger.info(f"📋 Order {request_id} found in completed results")
                return self._order_results[request_id]

            await asyncio.sleep(0.2)  # Check every 200ms

        # Check one more time before creating fallback
        if request_id in self._active_orders:
            if self.enable_logging:
                logger.success(
                    f" Order {request_id} found in active tracking (final check)"
                )
            return self._active_orders[request_id]

        if request_id in self._order_results:
            if self.enable_logging:
                logger.info(
                    f"📋 Order {request_id} found in completed results (final check)"
                )
            return self._order_results[request_id]

        # If timeout, create a fallback result with the original order data
        if self.enable_logging:
            logger.warning(
                f"⏰ Order {request_id} timed out waiting for server response, creating fallback result"
            )
        fallback_result = OrderResult(
            order_id=request_id,
            asset=order.asset,
            amount=order.amount,
            direction=order.direction,
            duration=order.duration,
            status=OrderStatus.ACTIVE,  # Assume it's active since it was placed
            placed_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=order.duration),
            error_message="Timeout waiting for server confirmation",
        )  # Store it in active orders in case server responds later
        self._active_orders[request_id] = fallback_result
        if self.enable_logging:
            logger.info(f"📝 Created fallback order result for {request_id}")
        return fallback_result

    async def check_win(
        self, order_id: str, max_wait_time: float = 300.0
    ) -> Optional[Dict[str, Any]]:
        """
        Check win functionality - waits for trade completion message

        Args:
            order_id: Order ID to check
            max_wait_time: Maximum time to wait for result (default 5 minutes)

        Returns:
            Dictionary with trade result or None if timeout/error
        """
        start_time = time.time()

        if self.enable_logging:
            logger.info(
                f"🔍 Starting check_win for order {order_id}, max wait: {max_wait_time}s"
            )

        while time.time() - start_time < max_wait_time:
            # Check if order is in completed results
            if order_id in self._order_results:
                result = self._order_results[order_id]
                if self.enable_logging:
                    logger.success(
                        f" Order {order_id} completed - Status: {result.status.value}, Profit: ${result.profit:.2f}"
                    )

                return {
                    "result": "win"
                    if result.status == OrderStatus.WIN
                    else "loss"
                    if result.status == OrderStatus.LOSE
                    else "draw",
                    "profit": result.profit if result.profit is not None else 0,
                    "order_id": order_id,
                    "completed": True,
                    "status": result.status.value,
                }

            # Check if order is still active (not expired yet)
            if order_id in self._active_orders:
                active_order = self._active_orders[order_id]
                time_remaining = (
                    active_order.expires_at - datetime.now()
                ).total_seconds()

                if time_remaining <= 0:
                    if self.enable_logging:
                        logger.info(
                            f"⏰ Order {order_id} expired but no result yet, continuing to wait..."
                        )
                else:
                    if (
                        self.enable_logging and int(time.time() - start_time) % 10 == 0
                    ):  # Log every 10 seconds
                        logger.debug(
                            f"⌛ Order {order_id} still active, expires in {time_remaining:.0f}s"
                        )

            await asyncio.sleep(1.0)  # Check every second

        # Timeout reached
        if self.enable_logging:
            logger.warning(
                f"⏰ check_win timeout for order {order_id} after {max_wait_time}s"
            )

        return {
            "result": "timeout",
            "order_id": order_id,
            "completed": False,
            "timeout": True,
        }

    async def _request_candles(
        self, asset: str, timeframe: int, count: int, end_time: datetime
    ):
        """Request candle data from server using the correct changeSymbol format"""

        # Create message data in the format expected by PocketOption for real-time candles
        data = {
            "asset": str(asset),
            "period": timeframe,  # timeframe in seconds
        }

        # Create the full message using changeSymbol
        message_data = ["changeSymbol", data]
        message = f"42{json.dumps(message_data)}"

        if self.enable_logging:
            logger.debug(f"Requesting candles with changeSymbol: {message}")

        # Create a future to wait for the response
        candle_future = asyncio.Future()
        request_id = f"{asset}_{timeframe}"

        # Store the future for this request
        if not hasattr(self, "_candle_requests"):
            self._candle_requests = {}
        self._candle_requests[request_id] = candle_future

        # Send the request using appropriate connection
        if self._is_persistent and self._keep_alive_manager:
            await self._keep_alive_manager.send_message(message)
        else:
            await self._websocket.send_message(message)

        try:
            # Wait for the response (with timeout)
            candles = await asyncio.wait_for(candle_future, timeout=10.0)
            return candles
        except asyncio.TimeoutError:
            if self.enable_logging:
                logger.warning(f"Candle request timed out for {asset}")
            return []
        finally:
            # Clean up the request
            if request_id in self._candle_requests:
                del self._candle_requests[request_id]

    def _parse_candles_data(self, candles_data: List[Any], asset: str, timeframe: int):
        """Parse candles data from server response"""
        candles = []

        try:
            if isinstance(candles_data, list):
                for candle_data in candles_data:
                    if isinstance(candle_data, (list, tuple)) and len(candle_data) >= 5:
                        # Server format: [timestamp, open, close, high, low]
                        candle = Candle(
                            timestamp=datetime.fromtimestamp(candle_data[0]),
                            open=float(candle_data[1]),
                            high=float(candle_data[3]),
                            low=float(candle_data[4]),
                            close=float(candle_data[2]),
                            volume=float(candle_data[5])
                            if len(candle_data) > 5
                            else 0.0,
                            asset=asset,
                            timeframe=timeframe,
                        )
                        candles.append(candle)

        except Exception as e:
            if self.enable_logging:
                logger.error(f"Error parsing candles data: {e}")

        return candles

    async def _on_json_data(self, data: Dict[str, Any]) -> None:
        """Handle detailed order data from JSON bytes messages"""
        if not isinstance(data, dict):
            return
        # Check if this is candles data response
        if "candles" in data and isinstance(data["candles"], list):
            # Find the corresponding candle request
            if hasattr(self, "_candle_requests"):
                # Try to match the request based on asset and period
                asset = data.get("asset")
                period = data.get("period")
                if asset and period:
                    request_id = f"{asset}_{period}"
                    if (
                        request_id in self._candle_requests
                        and not self._candle_requests[request_id].done()
                    ):
                        candles = self._parse_candles_data(
                            data["candles"], asset, period
                        )
                        self._candle_requests[request_id].set_result(candles)
                        if self.enable_logging:
                            logger.success(
                                f" Candles data received: {len(candles)} candles for {asset}"
                            )
                        del self._candle_requests[request_id]
                        return
            return

        # Check if this is detailed order data with requestId
        if "requestId" in data and "asset" in data and "amount" in data:
            request_id = str(data["requestId"])

            # Store mapping from server ID to request ID if server ID is present and valid
            if "id" in data and data["id"]:
                server_id = str(data["id"])
                if server_id:  # Ensure string is not empty
                    self._server_id_to_request_id[server_id] = request_id
                    if self.enable_logging:
                        logger.debug(f"Mapped server ID {server_id} to request ID {request_id}")

            # If this is a new order, add it to tracking
            if (
                request_id not in self._active_orders
                and request_id not in self._order_results
            ):
                order_result = OrderResult(
                    order_id=request_id,
                    asset=data.get("asset", "UNKNOWN"),
                    amount=float(data.get("amount", 0)),
                    direction=OrderDirection.CALL
                    if data.get("command", 0) == 0
                    else OrderDirection.PUT,
                    duration=int(data.get("time", 60)),
                    status=OrderStatus.ACTIVE,
                    placed_at=datetime.now(),
                    expires_at=datetime.now()
                    + timedelta(seconds=int(data.get("time", 60))),
                    profit=float(data.get("profit", 0)) if "profit" in data else None,
                    payout=data.get("payout"),
                )

                # Add to active orders
                self._active_orders[request_id] = order_result
                if self.enable_logging:
                    logger.success(
                        f" Order {request_id} added to tracking from JSON data"
                    )

                await self._emit_event("order_opened", data)

        # Check if this is order result data with deals
        elif "deals" in data and isinstance(data["deals"], list):
            for deal in data["deals"]:
                if isinstance(deal, dict) and "id" in deal:
                    server_deal_id = str(deal["id"])
                    
                    # Try to find the request_id for this server deal ID
                    request_id = self._server_id_to_request_id.get(server_deal_id)
                    
                    # If we have a mapping, use request_id to find the order
                    # Otherwise, fall back to trying server_deal_id directly
                    lookup_id = request_id or server_deal_id
                    
                    if lookup_id in self._active_orders:
                        active_order = self._active_orders[lookup_id]
                        profit = float(deal.get("profit", 0))

                        # Determine status
                        if profit > 0:
                            status = OrderStatus.WIN
                        elif profit < 0:
                            status = OrderStatus.LOSE
                        else:
                            status = OrderStatus.LOSE  # Default for zero profit

                        result = OrderResult(
                            order_id=active_order.order_id,
                            asset=active_order.asset,
                            amount=active_order.amount,
                            direction=active_order.direction,
                            duration=active_order.duration,
                            status=status,
                            placed_at=active_order.placed_at,
                            expires_at=active_order.expires_at,
                            profit=profit,
                            payout=deal.get("payout"),
                        )

                        # Move from active to completed - use the original order_id (request_id)
                        self._order_results[active_order.order_id] = result
                        del self._active_orders[lookup_id]
                        
                        # Clean up the server ID mapping
                        if request_id and server_deal_id in self._server_id_to_request_id:
                            del self._server_id_to_request_id[server_deal_id]

                        if self.enable_logging:
                            logger.success(
                                f" Order {active_order.order_id} completed via JSON data: {status.value} - Profit: ${profit:.2f}"
                            )
                            await self._emit_event("order_closed", result)

    async def _emit_event(self, event: str, data: Any) -> None:
        """Emit event to registered callbacks"""
        if event in self._event_callbacks:
            for callback in self._event_callbacks[event]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(data)
                    else:
                        callback(data)
                except Exception as e:
                    if self.enable_logging:
                        logger.error(f"Error in event callback for {event}: {e}")

    # Event handlers
    async def _on_authenticated(self, data: Dict[str, Any]) -> None:
        """Handle authentication success"""
        if self.enable_logging:
            logger.success(" Successfully authenticated with PocketOption")
        self._connection_stats["successful_connections"] += 1
        await self._emit_event("authenticated", data)

    async def _on_balance_updated(self, data: Dict[str, Any]) -> None:
        """Handle balance update"""
        try:
            balance = Balance(
                balance=float(data.get("balance", 0)),
                currency=data.get("currency", "USD"),
                is_demo=self.is_demo,
            )
            self._balance = balance
            if self.enable_logging:
                logger.info(f"Balance updated: ${balance.balance:.2f}")
            await self._emit_event("balance_updated", balance)
        except Exception as e:
            if self.enable_logging:
                logger.error(f"Failed to parse balance data: {e}")

    async def _on_balance_data(self, data: Dict[str, Any]) -> None:
        """Handle balance data message"""
        # This is similar to balance_updated but for different message format
        await self._on_balance_updated(data)

    async def _on_order_opened(self, data: Dict[str, Any]) -> None:
        """Handle order opened event"""
        if self.enable_logging:
            logger.info(f"Order opened: {data}")
        await self._emit_event("order_opened", data)

    async def _on_order_closed(self, data: Dict[str, Any]) -> None:
        """Handle order closed event"""
        if self.enable_logging:
            logger.info(f"📊 Order closed: {data}")
        await self._emit_event("order_closed", data)

    async def _on_stream_update(self, data: Dict[str, Any]) -> None:
        """Handle stream update event - includes real-time candle data"""
        if self.enable_logging:
            logger.debug(f"📡 Stream update: {data}")

        # Check if this is candle data from changeSymbol subscription
        if (
            "asset" in data
            and "period" in data
            and ("candles" in data or "data" in data)
        ):
            await self._handle_candles_stream(data)

        await self._emit_event("stream_update", data)

    async def _on_candles_received(self, data: Dict[str, Any]) -> None:
        """Handle candles data received"""
        if self.enable_logging:
            logger.info(f"🕯️ Candles received with data: {type(data)}")
        # Check if we have pending candle requests
        if hasattr(self, "_candle_requests") and self._candle_requests:
            try:
                for request_id, future in list(self._candle_requests.items()):
                    if not future.done():
                        parts = request_id.split("_")
                        if len(parts) >= 2:
                            asset = "_".join(parts[:-1])
                            timeframe = int(parts[-1])
                            candles = self._parse_candles_data(
                                data.get("candles", []), asset, timeframe
                            )
                            if self.enable_logging:
                                logger.info(
                                    f"🕯️ Parsed {len(candles)} candles from response"
                                )
                            future.set_result(candles)
                            if self.enable_logging:
                                logger.debug(f"Resolved candle request: {request_id}")
                            break
            except Exception as e:
                if self.enable_logging:
                    logger.error(f"Error processing candles data: {e}")
                for request_id, future in list(self._candle_requests.items()):
                    if not future.done():
                        future.set_result([])
                        break
        await self._emit_event("candles_received", data)

    async def _on_disconnected(self, data: Dict[str, Any]) -> None:
        """Handle disconnection event"""
        if self.enable_logging:
            logger.warning("Disconnected from PocketOption")
        await self._emit_event("disconnected", data)

    async def _handle_candles_stream(self, data: Dict[str, Any]) -> None:
        """Handle candle data from stream updates (changeSymbol responses)"""
        try:
            asset = data.get("asset")
            period = data.get("period")
            if not asset or not period:
                return
            request_id = f"{asset}_{period}"
            if self.enable_logging:
                logger.info(f"🕯️ Processing candle stream for {asset} ({period}s)")
            if (
                hasattr(self, "_candle_requests")
                and request_id in self._candle_requests
            ):
                future = self._candle_requests[request_id]
                if not future.done():
                    candles = self._parse_stream_candles(data, asset, period)
                    if candles:
                        future.set_result(candles)
                        if self.enable_logging:
                            logger.info(
                                f"🕯️ Resolved candle request for {asset} with {len(candles)} candles"
                            )
                del self._candle_requests[request_id]
        except Exception as e:
            if self.enable_logging:
                logger.error(f"Error handling candles stream: {e}")

    def _parse_stream_candles(
        self, stream_data: Dict[str, Any], asset: str, timeframe: int
    ):
        """Parse candles from stream update data (changeSymbol response)"""
        candles = []
        try:
            candle_data = stream_data.get("data") or stream_data.get("candles") or []
            if isinstance(candle_data, list):
                for item in candle_data:
                    if isinstance(item, dict):
                        candle = Candle(
                            timestamp=datetime.fromtimestamp(item.get("time", 0)),
                            open=float(item.get("open", 0)),
                            high=float(item.get("high", 0)),
                            low=float(item.get("low", 0)),
                            close=float(item.get("close", 0)),
                            volume=float(item.get("volume", 0)),
                            asset=asset,
                            timeframe=timeframe,
                        )
                        candles.append(candle)
                    elif isinstance(item, (list, tuple)) and len(item) >= 5:
                        # Server format: [timestamp, open, close, high, low]
                        candle = Candle(
                            timestamp=datetime.fromtimestamp(item[0]),
                            open=float(item[1]),
                            high=float(item[3]),
                            low=float(item[4]),
                            close=float(item[2]),
                            volume=float(item[5]) if len(item) > 5 else 0.0,
                            asset=asset,
                            timeframe=timeframe,
                        )
                        candles.append(candle)
            candles.sort(key=lambda x: x.timestamp)
        except Exception as e:
            if self.enable_logging:
                logger.error(f"Error parsing stream candles: {e}")
        return candles

    async def _on_keep_alive_connected(self, data: Dict[str, Any] = None):
        """Handle event when keep-alive connection is established"""
        logger.info("Keep-alive connection established")

        # Initialize data after connection
        await self._initialize_data()

        # Emit event
        for callback in self._event_callbacks.get("connected", []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error(f"Error in connected callback: {e}")

    async def _on_keep_alive_reconnected(self, data: Dict[str, Any] = None):
        """Handle event when keep-alive connection is re-established"""
        logger.info("Keep-alive connection re-established")

        # Re-initialize data
        await self._initialize_data()

        # Emit event
        for callback in self._event_callbacks.get("reconnected", []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error(f"Error in reconnected callback: {e}")

    async def _on_keep_alive_message(self, data: Dict[str, Any] = None):
        """Handle messages received via keep-alive connection"""
        # Extract message from data dictionary
        message = data.get("message", "") if isinstance(data, dict) else str(data) if data else ""
        # Process the message
        if message.startswith("42"):
            try:
                # Parse the message (remove the 42 prefix and parse JSON)
                data_str = message[2:]
                data = json.loads(data_str)

                if isinstance(data, list) and len(data) >= 2:
                    event_type = data[0]
                    event_data = data[1]

                    # Process different event types
                    if event_type == "authenticated":
                        await self._on_authenticated(event_data)
                    elif event_type == "balance_data":
                        await self._on_balance_data(event_data)
                    elif event_type == "balance_updated":
                        await self._on_balance_updated(event_data)
                    elif event_type == "order_opened":
                        await self._on_order_opened(event_data)
                    elif event_type == "order_closed":
                        await self._on_order_closed(event_data)
                    elif event_type == "stream_update":
                        await self._on_stream_update(event_data)
            except Exception as e:
                logger.error(f"Error processing keep-alive message: {e}")

        # Emit raw message event
        for callback in self._event_callbacks.get("message", []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(message)
                else:
                    callback(message)
            except Exception as e:
                logger.error(f"Error in message callback: {e}")

    async def _attempt_reconnection(self, max_attempts: int = 3) -> bool:
        """
        Attempt to reconnect to PocketOption

        Args:
            max_attempts: Maximum number of reconnection attempts

        Returns:
            bool: True if reconnection was successful
        """
        logger.info(f"Attempting reconnection (max {max_attempts} attempts)...")

        for attempt in range(max_attempts):
            try:
                logger.info(f"Reconnection attempt {attempt + 1}/{max_attempts}")

                # Disconnect first to clean up
                if self._is_persistent and self._keep_alive_manager:
                    await self._keep_alive_manager.disconnect()
                else:
                    await self._websocket.disconnect()

                # Wait a bit before reconnecting
                await asyncio.sleep(2 + attempt)  # Progressive delay

                # Attempt to reconnect
                if self.persistent_connection:
                    success = await self._start_persistent_connection()
                else:
                    success = await self._start_regular_connection()

                if success:
                    logger.info(f" Reconnection successful on attempt {attempt + 1}")

                    # Trigger reconnected event
                    await self._emit_event("reconnected", {})
                    return True
                else:
                    logger.warning(f"Reconnection attempt {attempt + 1} failed")

            except Exception as e:
                logger.error(
                    f"Reconnection attempt {attempt + 1} failed with error: {e}"
                )

        logger.error(f"All {max_attempts} reconnection attempts failed")
        return False
