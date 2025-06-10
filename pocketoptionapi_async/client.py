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
    Balance, Candle, Order, OrderResult, OrderStatus, OrderDirection,
    ConnectionStatus, ServerTime
)
from .constants import ASSETS, REGIONS, TIMEFRAMES, API_LIMITS
from .exceptions import (
    PocketOptionError, ConnectionError, AuthenticationError,
    OrderError, TimeoutError, InvalidParameterError
)


class AsyncPocketOptionClient:
    """
    Professional async PocketOption API client with modern Python practices
    """
    
    def __init__(self, ssid: str, is_demo: bool = True, region: Optional[str] = None, 
                 uid: int = 0, platform: int = 1, is_fast_history: bool = True,
                 persistent_connection: bool = False, auto_reconnect: bool = True, 
                 enable_logging: bool = True):
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
          # Parse SSID if it's a complete auth message
        self._original_demo = None  # Store original demo value from SSID
        if ssid.startswith('42["auth",'):
            self._parse_complete_ssid(ssid)
        else:
            # Treat as raw session ID
            self.session_id = ssid
            self._complete_ssid = None
            
        # Core components
        self._websocket = AsyncWebSocketClient()
        self._balance: Optional[Balance] = None
        self._orders: Dict[str, OrderResult] = {}
        self._active_orders: Dict[str, OrderResult] = {}
        self._order_results: Dict[str, OrderResult] = {}
        self._candles_cache: Dict[str, List[Candle]] = {}
        self._server_time: Optional[ServerTime] = None
        self._event_callbacks: Dict[str, List[Callable]] = defaultdict(list)
          # Setup event handlers for websocket messages
        self._setup_event_handlers()
        
        # Add handler for JSON data messages (contains detailed order data)
        self._websocket.add_event_handler('json_data', self._on_json_data)
          # Enhanced monitoring and error handling
        from .monitoring import error_monitor, health_checker
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
            'total_connections': 0,
            'successful_connections': 0,
            'total_reconnects': 0,
            'last_ping_time': None,
            'messages_sent': 0,
            'messages_received': 0,
            'connection_start_time': None
        }
        
        logger.info(f"Initialized PocketOption client (demo={is_demo}, uid={self.uid}, persistent={persistent_connection}) with enhanced monitoring" if enable_logging else "")

    def _setup_event_handlers(self):
        """Setup WebSocket event handlers"""
        self._websocket.add_event_handler('authenticated', self._on_authenticated)
        self._websocket.add_event_handler('balance_updated', self._on_balance_updated)
        self._websocket.add_event_handler('balance_data', self._on_balance_data)  # Add balance_data handler
        self._websocket.add_event_handler('order_opened', self._on_order_opened)
        self._websocket.add_event_handler('order_closed', self._on_order_closed)
        self._websocket.add_event_handler('stream_update', self._on_stream_update)
        self._websocket.add_event_handler('candles_received', self._on_candles_received)
        self._websocket.add_event_handler('disconnected', self._on_disconnected)

    async def connect(self, regions: Optional[List[str]] = None, persistent: bool = None) -> bool:
        """
        Connect to PocketOption with multiple region support
        
        Args:
            regions: List of regions to try (uses defaults if None)
            persistent: Override persistent connection setting
            
        Returns:
            bool: True if connected successfully
        """
        logger.info("🔌 Connecting to PocketOption...")
          # Update persistent setting if provided
        if persistent is not None:
            self.persistent_connection = persistent
        
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
                message=f"Connection failed: {e}"
            )
            return False

    async def _start_regular_connection(self, regions: Optional[List[str]] = None) -> bool:
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
                regions = [name for name, url in all_regions.items() if "DEMO" not in name.upper()]
                logger.info(f"Live mode: Using non-demo regions: {regions}")
          # Update connection stats
        self._connection_stats['total_connections'] += 1
        self._connection_stats['connection_start_time'] = time.time()
        
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
                    logger.info(f"✅ Connected to region: {region}")
                    
                    # Wait for authentication
                    await self._wait_for_authentication()
                    
                    # Initialize data
                    await self._initialize_data()
                    
                    # Start keep-alive tasks
                    await self._start_keep_alive_tasks()
                    
                    self._connection_stats['successful_connections'] += 1
                    logger.info("Successfully connected and authenticated")
                    return True
                    
            except Exception as e:
                logger.warning(f"Failed to connect to region {region}: {e}")
                continue
        
        return False

    async def _start_persistent_connection(self, regions: Optional[List[str]] = None) -> bool:
        """Start persistent connection with keep-alive (like old API)"""
        logger.info("🚀 Starting persistent connection with automatic keep-alive...")
        
        # Import the keep-alive manager
        import sys
        sys.path.append('/Users/vigowalker/PocketOptionAPI-3')
        from connection_keep_alive import ConnectionKeepAlive
        
        # Create keep-alive manager
        complete_ssid = self.raw_ssid
        self._keep_alive_manager = ConnectionKeepAlive(complete_ssid, self.is_demo)
        
        # Add event handlers
        self._keep_alive_manager.add_event_handler('connected', self._on_keep_alive_connected)
        self._keep_alive_manager.add_event_handler('reconnected', self._on_keep_alive_reconnected)
        self._keep_alive_manager.add_event_handler('message_received', self._on_keep_alive_message)
        
        # Connect with keep-alive
        success = await self._keep_alive_manager.connect_with_keep_alive(regions)
        
        if success:
            self._is_persistent = True
            logger.info("✅ Persistent connection established successfully")
            return True
        else:
            logger.error("❌ Failed to establish persistent connection")
            return False

    async def _start_keep_alive_tasks(self):
        """Start keep-alive tasks for regular connection"""
        logger.info("🔄 Starting keep-alive tasks for regular connection...")
        
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
                self._connection_stats['last_ping_time'] = time.time()
                await asyncio.sleep(20)  # Ping every 20 seconds
            except Exception as e:
                logger.warning(f"Ping failed: {e}")
                break

    async def _reconnection_monitor(self):
        """Monitor and handle reconnections for regular connections"""
        while self.auto_reconnect and not self._is_persistent:
            await asyncio.sleep(30)  # Check every 30 seconds
            
            if not self.is_connected:
                logger.info("🔄 Connection lost, attempting reconnection...")
                self._connection_stats['total_reconnects'] += 1
                
                try:
                    success = await self._start_regular_connection()
                    if success:
                        logger.info("✅ Reconnection successful")
                    else:
                        logger.error("❌ Reconnection failed")
                        await asyncio.sleep(10)  # Wait before next attempt
                except Exception as e:
                    logger.error(f"Reconnection error: {e}")
                    await asyncio.sleep(10)

    async def disconnect(self) -> None:
        """Disconnect from PocketOption and cleanup all resources"""
        logger.info("🔌 Disconnecting from PocketOption...")
        
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
        if not self._balance or (datetime.now() - self._balance.last_updated).seconds > 60:
            await self._request_balance_update()
            
            # Wait a bit for balance to be received
            await asyncio.sleep(1)
        
        if not self._balance:
            raise PocketOptionError("Balance data not available")
        
        return self._balance

    async def place_order(self, asset: str, amount: float, direction: OrderDirection, 
                         duration: int) -> OrderResult:
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
                request_id=order_id  # Use request_id, not order_id
            )            # Send order
            await self._send_order(order)
            
            # Wait for result (this will either get the real server response or create a fallback)
            result = await self._wait_for_order_result(order_id, order)
            
            # Don't store again - _wait_for_order_result already handles storage
            logger.info(f"Order placed: {result.order_id} - {result.status}")
            return result
            
        except Exception as e:
            logger.error(f"Order placement failed: {e}")
            raise OrderError(f"Failed to place order: {e}")

    async def get_candles(self, asset: str, timeframe: Union[str, int], 
                         count: int = 100, end_time: Optional[datetime] = None) -> List[Candle]:
        """
        Get historical candle data
        
        Args:
            asset: Asset symbol
            timeframe: Timeframe (e.g., "1m", "5m", 60)
            count: Number of candles to retrieve
            end_time: End time for data (defaults to now)
            
        Returns:
            List[Candle]: Historical candle data
        """
        if not self.is_connected:
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
        
        try:
            # Request candle data
            candles = await self._request_candles(asset, timeframe_seconds, count, end_time)
            
            # Cache results
            cache_key = f"{asset}_{timeframe_seconds}"
            self._candles_cache[cache_key] = candles
            
            logger.info(f"Retrieved {len(candles)} candles for {asset}")
            return candles
            
        except Exception as e:
            logger.error(f"Failed to get candles: {e}")
            raise PocketOptionError(f"Failed to get candles: {e}")

    async def get_candles_dataframe(self, asset: str, timeframe: Union[str, int], 
                                   count: int = 100, end_time: Optional[datetime] = None) -> pd.DataFrame:
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
            data.append({
                'timestamp': candle.timestamp,
                'open': candle.open,
                'high': candle.high,
                'low': candle.low,
                'close': candle.close,
                'volume': candle.volume
            })
        df = pd.DataFrame(data)
        
        if not df.empty:
            df.set_index('timestamp', inplace=True)
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
        # First check active orders
        if order_id in self._active_orders:
            return self._active_orders[order_id]
        
        # Then check completed orders
        if order_id in self._order_results:
            return self._order_results[order_id]
            
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
            stats.update({
                'websocket_connected': self._websocket.is_connected,
                'connection_info': self._websocket.connection_info
            })
            
        return stats    # Private methods
    
    def _format_session_message(self) -> str:
        """Format session authentication message"""
        # Always create auth message from components using constructor parameters
        # This ensures is_demo parameter is respected regardless of SSID format
        auth_data = {
            "session": self.session_id,
            "isDemo": 1 if self.is_demo else 0,
            "uid": self.uid,
            "platform": self.platform
        }
        
        if self.is_fast_history:
            auth_data["isFastHistory"] = True
        
        return f'42["auth",{json.dumps(auth_data)}]'

    def _parse_complete_ssid(self, ssid: str) -> None:
        """Parse complete SSID auth message to extract components"""
        try:
            # Extract JSON part
            json_start = ssid.find('{')
            json_end = ssid.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                json_part = ssid[json_start:json_end]
                data = json.loads(json_part)
                
                self.session_id = data.get('session', '')
                # Store original demo value from SSID, but don't override the constructor parameter
                self._original_demo = bool(data.get('isDemo', 1))
                # Keep the is_demo value from constructor - don't override it
                self.uid = data.get('uid', 0)
                self.platform = data.get('platform', 1)
                # Don't store complete SSID - we'll reconstruct it with correct demo value
                self._complete_ssid = None
        except Exception as e:
            logger.warning(f"Failed to parse SSID: {e}")
            self.session_id = ssid
            self._complete_ssid = None

    async def _wait_for_authentication(self, timeout: float = 10.0) -> None:
        """Wait for authentication to complete (like old API)"""
        auth_received = False
        
        def on_auth(data):
            nonlocal auth_received
            auth_received = True
            
        # Add temporary handler
        self._websocket.add_event_handler('authenticated', on_auth)
        
        try:
            # Wait for authentication
            start_time = time.time()
            while not auth_received and (time.time() - start_time) < timeout:
                await asyncio.sleep(0.1)
            
            if not auth_received:
                raise AuthenticationError("Authentication timeout")
                
        finally:
            # Remove temporary handler
            self._websocket.remove_event_handler('authenticated', on_auth)

    async def _initialize_data(self) -> None:
        """Initialize client data after connection"""
        # Request initial balance
        await self._request_balance_update()
        
        # Setup time synchronization
        await self._setup_time_sync()

    async def _request_balance_update(self) -> None:
        """Request balance update from server"""
        message = '42["getBalance"]'
        await self._websocket.send_message(message)

    async def _setup_time_sync(self) -> None:
        """Setup server time synchronization"""
        # This would typically involve getting server timestamp
        # For now, create a basic time sync object
        local_time = datetime.now().timestamp()
        self._server_time = ServerTime(
            server_timestamp=local_time,
            local_timestamp=local_time,
            offset=0.0
        )

    def _validate_order_parameters(self, asset: str, amount: float, 
                                  direction: OrderDirection, duration: int) -> None:
        """Validate order parameters"""
        if asset not in ASSETS:
            raise InvalidParameterError(f"Invalid asset: {asset}")
        
        if amount < API_LIMITS['min_order_amount'] or amount > API_LIMITS['max_order_amount']:
            raise InvalidParameterError(                f"Amount must be between {API_LIMITS['min_order_amount']} and {API_LIMITS['max_order_amount']}"
            )
        
        if duration < API_LIMITS['min_duration'] or duration > API_LIMITS['max_duration']:
            raise InvalidParameterError(
                f"Duration must be between {API_LIMITS['min_duration']} and {API_LIMITS['max_duration']} seconds"
            )

    async def _send_order(self, order: Order) -> None:
        """Send order to server"""
        # Format asset name with # prefix if not already present
        asset_name = order.asset
        
        # Create the message in the correct PocketOption format
        message = f'42["openOrder",{{"asset":"{asset_name}","amount":{order.amount},"action":"{order.direction.value}","isDemo":{1 if self.is_demo else 0},"requestId":"{order.request_id}","optionType":100,"time":{order.duration}}}]'
        await self._websocket.send_message(message)
        if self.enable_logging:
            logger.debug(f"Sent order: {message}")

    async def _wait_for_order_result(self, request_id: str, order: Order, timeout: float = 30.0) -> OrderResult:
        """Wait for order execution result"""
        start_time = time.time()
        
        # Wait for order to appear in tracking system
        while time.time() - start_time < timeout:
            # Check if order was added to active orders (by _on_order_opened or _on_json_data)
            if request_id in self._active_orders:
                if self.enable_logging:
                    logger.success(f"✅ Order {request_id} found in active tracking")
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
                logger.success(f"✅ Order {request_id} found in active tracking (final check)")
            return self._active_orders[request_id]
        
        if request_id in self._order_results:
            if self.enable_logging:
                logger.info(f"📋 Order {request_id} found in completed results (final check)")
            return self._order_results[request_id]
        
        # If timeout, create a fallback result with the original order data
        if self.enable_logging:
            logger.warning(f"⏰ Order {request_id} timed out waiting for server response, creating fallback result")
        fallback_result = OrderResult(
            order_id=request_id,
            asset=order.asset,
            amount=order.amount,
            direction=order.direction,
            duration=order.duration,
            status=OrderStatus.ACTIVE,  # Assume it's active since it was placed
            placed_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=order.duration),
            error_message="Timeout waiting for server confirmation"
        )
          # Store it in active orders in case server responds later
        self._active_orders[request_id] = fallback_result
        if self.enable_logging:
            logger.info(f"📝 Created fallback order result for {request_id}")
        return fallback_result

    async def _request_candles(self, asset: str, timeframe: int, count: int, 
                              end_time: datetime) -> List[Candle]:
        """Request candle data from server using the correct PocketOption format"""
        
        # Convert end_time to timestamp (similar to original API)
        end_timestamp = int(end_time.timestamp())
        
        # Create message data in the format expected by PocketOption
        data = {
            "asset": str(asset),
            "index": end_timestamp,
            "offset": count,  # number of candles
            "period": timeframe,  # timeframe in seconds
            "time": end_timestamp  # end time timestamp
        }
        
        # Create the full message
        message_data = ["loadHistoryPeriod", data]
        message = f'42["sendMessage",{json.dumps(message_data)}]'
        
        if self.enable_logging:
            logger.debug(f"Requesting candles: {message}")
        
        # Create a future to wait for the response
        candle_future = asyncio.Future()
        request_id = f"{asset}_{timeframe}_{end_timestamp}"
        
        # Store the future for this request
        if not hasattr(self, '_candle_requests'):
            self._candle_requests = {}
        self._candle_requests[request_id] = candle_future
        
        # Send the request
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

    def _parse_candles_data(self, candles_data: List[Any]) -> List[Candle]:
        """Parse candles data from server response"""
        candles = []
        
        try:
            if isinstance(candles_data, list):
                for candle_data in candles_data:
                    if isinstance(candle_data, (list, tuple)) and len(candle_data) >= 6:
                        # Expected format: [timestamp, open, close, high, low, volume]
                        candle = Candle(
                            timestamp=datetime.fromtimestamp(candle_data[0]),
                            open=float(candle_data[1]),
                            close=float(candle_data[2]),
                            high=float(candle_data[3]),
                            low=float(candle_data[4]),
                            volume=float(candle_data[5]) if len(candle_data) > 5 else 0.0
                        )
                        candles.append(candle)
                    elif isinstance(candle_data, dict):
                        # Handle dict format
                        candle = Candle(
                            timestamp=datetime.fromtimestamp(candle_data.get('timestamp', 0)),
                            open=float(candle_data.get('open', 0)),
                            close=float(candle_data.get('close', 0)),
                            high=float(candle_data.get('high', 0)),
                            low=float(candle_data.get('low', 0)),
                            volume=float(candle_data.get('volume', 0))
                        )
                        candles.append(candle)
        except Exception as e:
            if self.enable_logging:
                logger.error(f"Error parsing candles data: {e}")
        
        return candles

    # ...existing code...

    async def _on_json_data(self, data: Dict[str, Any]) -> None:
        """Handle detailed order data from JSON bytes messages"""
        if not isinstance(data, dict):
            return
        
        # Check if this is candles data response
        if "history" in data and isinstance(data["history"], list):
            # Find the corresponding candle request
            if hasattr(self, '_candle_requests'):
                # Try to match the request - in a real implementation you'd need better matching
                for request_id, future in list(self._candle_requests.items()):
                    if not future.done():
                        candles = self._parse_candles_data(data["history"])
                        future.set_result(candles)
                        if self.enable_logging:
                            logger.success(f"✅ Candles data received: {len(candles)} candles")
                        break
            return
            
        # Check if this is detailed order data with requestId
        if "requestId" in data and "asset" in data and "amount" in data:
            request_id = str(data["requestId"])
            
            # If this is a new order, add it to tracking
            if request_id not in self._active_orders and request_id not in self._order_results:
                order_result = OrderResult(
                    order_id=request_id,
                    asset=data.get('asset', 'UNKNOWN'),
                    amount=float(data.get('amount', 0)),
                    direction=OrderDirection.CALL if data.get('command', 0) == 0 else OrderDirection.PUT,
                    duration=int(data.get('time', 60)),
                    status=OrderStatus.ACTIVE,
                    placed_at=datetime.now(),
                    expires_at=datetime.now() + timedelta(seconds=int(data.get('time', 60))),
                    profit=float(data.get('profit', 0)) if 'profit' in data else None,
                    payout=data.get('payout')
                )
                
                # Add to active orders
                self._active_orders[request_id] = order_result
                if self.enable_logging:
                    logger.success(f"✅ Order {request_id} added to tracking from JSON data")
                
                await self._emit_event('order_opened', data)
                
        # Check if this is order result data with deals
        elif "deals" in data and isinstance(data["deals"], list):
            for deal in data["deals"]:
                if isinstance(deal, dict) and "id" in deal:
                    order_id = str(deal["id"])
                    
                    if order_id in self._active_orders:
                        active_order = self._active_orders[order_id]
                        profit = float(deal.get('profit', 0))
                        
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
                            payout=deal.get('payout')
                        )
                        
                        # Move from active to completed
                        self._order_results[order_id] = result
                        del self._active_orders[order_id]
                        
                        if self.enable_logging:
                            logger.success(f"✅ Order {order_id} completed via JSON data: {status.value} - Profit: ${profit:.2f}")
                        await self._emit_event('order_closed', result)

    def _parse_candles_data(self, history_data: List[Dict]) -> List[Candle]:
        """Parse candles data from history response"""
        candles = []
        for item in history_data:
            if isinstance(item, dict):
                candle = Candle(
                    timestamp=datetime.fromtimestamp(item.get('time', 0)),
                    open=float(item.get('open', 0)),
                    high=float(item.get('high', 0)),
                    low=float(item.get('low', 0)),
                    close=float(item.get('close', 0)),
                    volume=float(item.get('volume', 0))
                )
                candles.append(candle)
        return candles

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
            logger.success("✅ Successfully authenticated with PocketOption")
        self._connection_stats['successful_connections'] += 1
        await self._emit_event('authenticated', data)    
    async def _on_balance_updated(self, data: Dict[str, Any]) -> None:
        """Handle balance update"""
        try:
            balance = Balance(
                balance=float(data.get('balance', 0)),
                currency=data.get('currency', 'USD'),
                is_demo=self.is_demo
            )
            self._balance = balance
            if self.enable_logging:
                logger.info(f"💰 Balance updated: ${balance.balance:.2f}")
            await self._emit_event('balance_updated', balance)
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
            logger.info(f"📈 Order opened: {data}")
        await self._emit_event('order_opened', data)

    async def _on_order_closed(self, data: Dict[str, Any]) -> None:
        """Handle order closed event"""
        if self.enable_logging:
            logger.info(f"📊 Order closed: {data}")
        await self._emit_event('order_closed', data)

    async def _on_stream_update(self, data: Dict[str, Any]) -> None:
        """Handle stream update event"""
        if self.enable_logging:
            logger.debug(f"📡 Stream update: {data}")
        await self._emit_event('stream_update', data)

    async def _on_candles_received(self, data: Dict[str, Any]) -> None:
        """Handle candles data received"""
        if self.enable_logging:
            logger.info(f"🕯️ Candles received with data: {type(data)}")
        
        # Check if we have pending candle requests
        if hasattr(self, '_candle_requests') and self._candle_requests:
            # Parse the candles data
            try:
                candles = self._parse_candles_data(data)
                if self.enable_logging:
                    logger.info(f"🕯️ Parsed {len(candles)} candles from response")
                
                # Resolve any pending futures (take the first one for now)
                # In a more sophisticated implementation, we could match by asset/timeframe
                for request_id, future in list(self._candle_requests.items()):
                    if not future.done():
                        future.set_result(candles)
                        if self.enable_logging:
                            logger.debug(f"Resolved candle request: {request_id}")
                        break
                        
            except Exception as e:
                if self.enable_logging:
                    logger.error(f"Error processing candles data: {e}")
                # Resolve futures with empty result
                for request_id, future in list(self._candle_requests.items()):
                    if not future.done():
                        future.set_result([])
                        break
        
        await self._emit_event('candles_received', data)

    async def _on_disconnected(self, data: Dict[str, Any]) -> None:
        """Handle disconnection event"""
        if self.enable_logging:
            logger.warning("🔌 Disconnected from PocketOption")
        await self._emit_event('disconnected', data)
