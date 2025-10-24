"""
Enhanced Keep-Alive Connection Manager for PocketOption Async API
"""

import asyncio
from typing import Optional, List, Callable, Dict, Any
from datetime import datetime, timedelta
from loguru import logger
from websockets.exceptions import ConnectionClosed
from websockets.legacy.client import connect, WebSocketClientProtocol

#from models import ConnectionInfo, ConnectionStatus
from pocketoptionapi_async.models import ConnectionInfo, ConnectionStatus
from pocketoptionapi_async.constants import REGIONS

#from constants import REGIONS


class ConnectionKeepAlive:
    """
    Advanced connection keep-alive manager based on old API patterns
    """

    def __init__(self, ssid: str, is_demo: bool = True):
        self.ssid = ssid
        self.is_demo = is_demo

        # Connection state
        self.websocket: Optional[WebSocketClientProtocol] = None
        self.connection_info: Optional[ConnectionInfo] = None
        self.is_connected = False
        self.should_reconnect = True

        # Background tasks
        self._ping_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._message_task: Optional[asyncio.Task] = None
        self._health_task: Optional[asyncio.Task] = None

        # Keep-alive settings
        self.ping_interval = 20  # seconds (same as old API)
        self.reconnect_delay = 5  # seconds
        self.max_reconnect_attempts = 10
        self.current_reconnect_attempts = 0

        # Event handlers
        self._event_handlers: Dict[str, List[Callable]] = {}

        # Connection pool with multiple regions
        self.available_urls = (
            REGIONS.get_demo_regions() if is_demo else REGIONS.get_all()
        )
        self.current_url_index = 0

        # Statistics
        self.connection_stats = {
            "total_connections": 0,
            "successful_connections": 0,
            "total_reconnects": 0,
            "last_ping_time": None,
            "last_pong_time": None,
            "total_messages_sent": 0,
            "total_messages_received": 0,
        }

        logger.info(
            f"Initialized keep-alive manager with {len(self.available_urls)} available regions"
        )

    async def start_persistent_connection(self) -> bool:
        """
        Start a persistent connection with automatic keep-alive
        Similar to old API's daemon thread approach but with modern async
        """
        logger.info("Starting persistent connection with keep-alive...")

        try:
            # Initial connection
            if await self._establish_connection():
                # Start all background tasks
                await self._start_background_tasks()
                logger.success(
                    "Success: Persistent connection established with keep-alive active"
                )
                return True
            else:
                logger.error("Error: Failed to establish initial connection")
                return False

        except Exception as e:
            logger.error(f"Error: Error starting persistent connection: {e}")
            return False

    async def stop_persistent_connection(self):
        """Stop the persistent connection and all background tasks"""
        logger.info("Stopping persistent connection...")

        self.should_reconnect = False

        # Cancel all background tasks
        tasks = [
            self._ping_task,
            self._reconnect_task,
            self._message_task,
            self._health_task,
        ]
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Close connection
        if self.websocket:
            await self.websocket.close()
            self.websocket = None

        self.is_connected = False
        logger.info("Success: Persistent connection stopped")

    async def _establish_connection(self) -> bool:
        """
        Establish connection with fallback URLs (like old API)
        """
        for attempt in range(len(self.available_urls)):
            url = self.available_urls[self.current_url_index]

            try:
                logger.info(
                    f"Connecting: Attempting connection to {url} (attempt {attempt + 1})"
                )

                # SSL context (like old API)
                import ssl

                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

                # Connect with headers (like old API)
                self.websocket = await asyncio.wait_for(
                    connect(
                        url,
                        ssl=ssl_context,
                        extra_headers={
                            "Origin": "https://pocketoption.com",
                            "Cache-Control": "no-cache",
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        },
                        ping_interval=None,  # We handle pings manually
                        ping_timeout=None,
                        close_timeout=10,
                    ),
                    timeout=15.0,
                )

                # Update connection info
                region = self._extract_region_from_url(url)
                self.connection_info = ConnectionInfo(
                    url=url,
                    region=region,
                    status=ConnectionStatus.CONNECTED,
                    connected_at=datetime.now(),
                    reconnect_attempts=self.current_reconnect_attempts,
                )

                self.is_connected = True
                self.current_reconnect_attempts = 0
                self.connection_stats["total_connections"] += 1
                self.connection_stats["successful_connections"] += 1

                # Send initial handshake (like old API)
                await self._send_handshake()

                logger.success(f"Success: Connected to {region} region successfully")
                await self._emit_event("connected", {"url": url, "region": region})

                return True

            except Exception as e:
                logger.warning(f"Caution: Failed to connect to {url}: {e}")

                # Try next URL
                self.current_url_index = (self.current_url_index + 1) % len(
                    self.available_urls
                )

                if self.websocket:
                    try:
                        await self.websocket.close()
                    except Exception:
                        pass
                    self.websocket = None

                await asyncio.sleep(1)  # Brief delay before next attempt

        return False

    async def _send_handshake(self):
        """Send initial handshake sequence (like old API)"""
        try:
            if not self.websocket:
                raise RuntimeError("Handshake called with no websocket connection.")
            # Wait for initial connection message
            initial_message = await asyncio.wait_for(
                self.websocket.recv(), timeout=10.0
            )
            logger.debug(f"Received initial: {initial_message}")

            # Send handshake sequence (like old API)
            await self.websocket.send("40")
            await asyncio.sleep(0.1)

            # Wait for connection establishment
            conn_message = await asyncio.wait_for(self.websocket.recv(), timeout=10.0)
            logger.debug(f"Received connection: {conn_message}")

            # Send SSID authentication
            await self.websocket.send(self.ssid)
            logger.debug("Handshake completed")

            self.connection_stats["total_messages_sent"] += 2

        except Exception as e:
            logger.error(f"Handshake failed: {e}")
            raise

    async def _start_background_tasks(self):
        """Start all background tasks (like old API's concurrent tasks)"""
        logger.info("Persistent: Starting background keep-alive tasks...")

        # Ping task (every 20 seconds like old API)
        self._ping_task = asyncio.create_task(self._ping_loop())

        # Message receiving task
        self._message_task = asyncio.create_task(self._message_loop())

        # Health monitoring task
        self._health_task = asyncio.create_task(self._health_monitor_loop())

        # Reconnection monitoring task
        self._reconnect_task = asyncio.create_task(self._reconnection_monitor())

        logger.success("Success: All background tasks started")

    async def _ping_loop(self):
        """
        Continuous ping loop (like old API's send_ping function)
        Sends '42["ps"]' every 20 seconds
        """
        logger.info("Ping: Starting ping loop...")

        while self.should_reconnect:
            try:
                if self.is_connected and self.websocket:
                    # Send ping message (exact format from old API)
                    await self.websocket.send('42["ps"]')
                    self.connection_stats["last_ping_time"] = datetime.now()
                    self.connection_stats["total_messages_sent"] += 1

                    logger.debug("Ping: Ping sent")

                await asyncio.sleep(self.ping_interval)

            except ConnectionClosed:
                logger.warning("Connecting: Connection closed during ping")
                self.is_connected = False
                break
            except Exception as e:
                logger.error(f"Error: Ping failed: {e}")
                self.is_connected = False
                break

    async def _message_loop(self):
        """
        Continuous message receiving loop (like old API's websocket_listener)
        """
        logger.info("Message: Starting message loop...")

        while self.should_reconnect:
            try:
                if self.is_connected and self.websocket:
                    try:
                        # Receive message with timeout
                        message = await asyncio.wait_for(
                            self.websocket.recv(), timeout=30.0
                        )

                        self.connection_stats["total_messages_received"] += 1
                        await self._process_message(message)

                    except asyncio.TimeoutError:
                        logger.debug("Message: Message receive timeout (normal)")
                        continue
                else:
                    await asyncio.sleep(1)

            except ConnectionClosed:
                logger.warning("Connecting: Connection closed during message receive")
                self.is_connected = False
                break
            except Exception as e:
                logger.error(f"Error: Message loop error: {e}")
                self.is_connected = False
                break

    async def _health_monitor_loop(self):
        """Monitor connection health and trigger reconnects if needed"""
        logger.info("Health: Starting health monitor...")

        while self.should_reconnect:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds

                if not self.is_connected:
                    logger.warning("Health: Health check: Connection lost")
                    continue

                # Check if we received a pong recently
                if self.connection_stats["last_ping_time"]:
                    time_since_ping = (
                        datetime.now() - self.connection_stats["last_ping_time"]
                    )
                    if time_since_ping > timedelta(
                        seconds=60
                    ):  # No response for 60 seconds
                        logger.warning(
                            "Health: Health check: No ping response, connection may be dead"
                        )
                        self.is_connected = False

                # Check WebSocket state
                if self.websocket and self.websocket.closed:
                    logger.warning("Health: Health check: WebSocket is closed")
                    self.is_connected = False

            except Exception as e:
                logger.error(f"Error: Health monitor error: {e}")

    async def _reconnection_monitor(self):
        """
        Monitor for disconnections and automatically reconnect (like old API)
        """
        logger.info("Persistent: Starting reconnection monitor...")

        while self.should_reconnect:
            try:
                await asyncio.sleep(5)  # Check every 5 seconds

                if not self.is_connected and self.should_reconnect:
                    logger.warning(
                        "Persistent: Detected disconnection, attempting reconnect..."
                    )

                    self.current_reconnect_attempts += 1
                    self.connection_stats["total_reconnects"] += 1

                    if self.current_reconnect_attempts <= self.max_reconnect_attempts:
                        logger.info(
                            f"Persistent: Reconnection attempt {self.current_reconnect_attempts}/{self.max_reconnect_attempts}"
                        )

                        # Clean up current connection
                        if self.websocket:
                            try:
                                await self.websocket.close()
                            except Exception:
                                pass
                            self.websocket = None

                        # Try to reconnect
                        success = await self._establish_connection()

                        if success:
                            logger.success("Success: Reconnection successful!")
                            await self._emit_event(
                                "reconnected",
                                {
                                    "attempt": self.current_reconnect_attempts,
                                    "url": self.connection_info.url
                                    if self.connection_info
                                    else None,
                                },
                            )
                        else:
                            logger.error(
                                f"Error: Reconnection attempt {self.current_reconnect_attempts} failed"
                            )
                            await asyncio.sleep(self.reconnect_delay)
                    else:
                        logger.error(
                            f"Error: Max reconnection attempts ({self.max_reconnect_attempts}) reached"
                        )
                        await self._emit_event(
                            "max_reconnects_reached",
                            {"attempts": self.current_reconnect_attempts},
                        )
                        break

            except Exception as e:
                logger.error(f"Error: Reconnection monitor error: {e}")

    async def _process_message(self, message):
        """Process incoming messages (like old API's on_message)"""
        try:
            # Convert bytes to string if needed
            if isinstance(message, bytes):
                message = message.decode("utf-8")

            logger.debug(f"Message: Received: {message[:100]}...")

            # Handle ping-pong (like old API)
            if message == "2":
                if self.websocket:
                    await self.websocket.send("3")
                    self.connection_stats["last_pong_time"] = datetime.now()
                    logger.debug("Ping: Pong sent")
                return

            # Handle authentication success (like old API)
            if "successauth" in message:
                logger.success("Success: Authentication successful")
                await self._emit_event("authenticated", {})
                return

            # Handle other message types
            await self._emit_event("message_received", {"message": message})

        except Exception as e:
            logger.error(f"Error: Error processing message: {e}")

    async def send_message(self, message: str) -> bool:
        """Send message with connection check"""
        try:
            if self.is_connected and self.websocket:
                await self.websocket.send(message)
                self.connection_stats["total_messages_sent"] += 1
                logger.debug(f"Message: Sent: {message[:50]}...")
                return True
            else:
                logger.warning("Caution: Cannot send message: not connected")
                return False
        except Exception as e:
            logger.error(f"Error: Failed to send message: {e}")
            self.is_connected = False
            return False

    def add_event_handler(self, event: str, handler: Callable):
        """Add event handler"""
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)

    async def _emit_event(self, event: str, data: Any):
        """Emit event to handlers"""
        if event in self._event_handlers:
            for handler in self._event_handlers[event]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(data)
                    else:
                        handler(data)
                except Exception as e:
                    logger.error(f"Error: Error in event handler for {event}: {e}")

    def _extract_region_from_url(self, url: str) -> str:
        """Extract region name from URL"""
        try:
            parts = url.split("//")[1].split(".")[0]
            if "api-" in parts:
                return parts.replace("api-", "").upper()
            elif "demo" in parts:
                return "DEMO"
            else:
                return "UNKNOWN"
        except Exception:
            return "UNKNOWN"

    def get_connection_stats(self) -> Dict[str, Any]:
        """Get detailed connection statistics"""
        return {
            **self.connection_stats,
            "is_connected": self.is_connected,
            "current_url": self.connection_info.url if self.connection_info else None,
            "current_region": self.connection_info.region
            if self.connection_info
            else None,
            "reconnect_attempts": self.current_reconnect_attempts,
            "uptime": (
                datetime.now() - self.connection_info.connected_at
                if self.connection_info and self.connection_info.connected_at
                else timedelta()
            ),
            "available_regions": len(self.available_urls),
        }

    async def connect_with_keep_alive(
        self, regions: Optional[List[str]] = None
    ) -> bool:
        """Establish a persistent connection with keep-alive, optionally using a list of regions."""
        # Optionally update available_urls if regions are provided
        if regions:
            # Assume regions are URLs or region names; adapt as needed
            self.available_urls = regions
            self.current_url_index = 0
        return await self.start_persistent_connection()

    async def disconnect(self) -> None:
        """Disconnect and clean up persistent connection."""
        await self.stop_persistent_connection()

    def get_stats(self) -> Dict[str, Any]:
        """Return connection statistics (alias for get_connection_stats)."""
        return self.get_connection_stats()


async def demo_keep_alive():
    """Demo of the keep-alive connection manager"""

    # Example complete SSID
    ssid = r'42["auth",{"session":"n1p5ah5u8t9438rbunpgrq0hlq","isDemo":1,"uid":0,"platform":1}]'

    # Create keep-alive manager
    keep_alive = ConnectionKeepAlive(ssid, is_demo=True)

    # Add event handlers
    async def on_connected(data):
        logger.success(f"Successfully: Connected to: {data}")

    async def on_reconnected(data):
        logger.success(f"Persistent: Reconnected after {data['attempt']} attempts")

    async def on_message(data):
        logger.info(f"Message: Message: {data['message'][:50]}...")

    keep_alive.add_event_handler("connected", on_connected)
    keep_alive.add_event_handler("reconnected", on_reconnected)
    keep_alive.add_event_handler("message_received", on_message)

    try:
        # Start persistent connection
        success = await keep_alive.start_persistent_connection()

        if success:
            logger.info(
                "Starting: Keep-alive connection started, will maintain connection automatically..."
            )

            # Let it run for a while to demonstrate keep-alive
            for i in range(60):  # Run for 1 minute
                await asyncio.sleep(1)

                # Print stats every 10 seconds
                if i % 10 == 0:
                    stats = keep_alive.get_connection_stats()
                    logger.info(
                        f"Statistics: Stats: Connected={stats['is_connected']}, "
                        f"Messages sent={stats['total_messages_sent']}, "
                        f"Messages received={stats['total_messages_received']}, "
                        f"Uptime={stats['uptime']}"
                    )

                # Send a test message every 30 seconds
                if i % 30 == 0 and i > 0:
                    await keep_alive.send_message('42["test"]')

        else:
            logger.error("Error: Failed to start keep-alive connection")

    finally:
        # Clean shutdown
        await keep_alive.stop_persistent_connection()


if __name__ == "__main__":
    logger.info("Testing: Testing Enhanced Keep-Alive Connection Manager")
    asyncio.run(demo_keep_alive())
