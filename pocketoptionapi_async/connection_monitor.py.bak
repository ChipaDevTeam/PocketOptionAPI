"""
Advanced Connection Monitor and Diagnostics Tool
Real-time monitoring, diagnostics, and performance analysis
"""

import asyncio
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, asdict
from collections import deque, defaultdict
import statistics
from loguru import logger

from client import AsyncPocketOptionClient


@dataclass
class ConnectionMetrics:
    """Connection performance metrics"""

    timestamp: datetime
    connection_time: float
    ping_time: Optional[float]
    message_count: int
    error_count: int
    region: str
    status: str


@dataclass
class PerformanceSnapshot:
    """Performance snapshot"""

    timestamp: datetime
    memory_usage_mb: float
    cpu_percent: float
    active_connections: int
    messages_per_second: float
    error_rate: float
    avg_response_time: float


class ConnectionMonitor:
    """Advanced connection monitoring and diagnostics"""

    def __init__(self, ssid: str, is_demo: bool = True):
        self.ssid = ssid
        self.is_demo = is_demo

        # Monitoring state
        self.is_monitoring = False
        self.monitor_task: Optional[asyncio.Task] = None
        self.client: Optional[AsyncPocketOptionClient] = None

        # Metrics storage
        self.connection_metrics: deque = deque(maxlen=1000)
        self.performance_snapshots: deque = deque(maxlen=500)
        self.error_log: deque = deque(maxlen=200)
        self.message_stats: Dict[str, int] = defaultdict(int)

        # Real-time stats
        self.start_time = datetime.now()
        self.total_messages = 0
        self.total_errors = 0
        self.last_ping_time = None
        self.ping_times: deque = deque(maxlen=100)

        # Event handlers
        self.event_handlers: Dict[str, List[Callable]] = defaultdict(list)

        # Performance tracking
        self.response_times: deque = deque(maxlen=100)
        self.connection_attempts = 0
        self.successful_connections = 0

    async def start_monitoring(self, persistent_connection: bool = True) -> bool:
        """Start real-time monitoring"""
        logger.info("Analysis: Starting connection monitoring...")

        try:
            # Initialize client
            self.client = AsyncPocketOptionClient(
                self.ssid,
                is_demo=self.is_demo,
                persistent_connection=persistent_connection,
                auto_reconnect=True,
            )

            # Setup event handlers
            self._setup_event_handlers()

            # Connect
            self.connection_attempts += 1
            start_time = time.time()

            success = await self.client.connect()

            if success:
                connection_time = time.time() - start_time
                self.successful_connections += 1

                # Record connection metrics
                self._record_connection_metrics(connection_time, "CONNECTED")

                # Start monitoring tasks
                self.is_monitoring = True
                self.monitor_task = asyncio.create_task(self._monitoring_loop())

                logger.success(
                    f"Success: Monitoring started (connection time: {connection_time:.3f}s)"
                )
                return True
            else:
                self._record_connection_metrics(0, "FAILED")
                logger.error("Error: Failed to connect for monitoring")
                return False

        except Exception as e:
            self.total_errors += 1
            self._record_error("monitoring_start", str(e))
            logger.error(f"Error: Failed to start monitoring: {e}")
            return False

    async def stop_monitoring(self):
        """Stop monitoring"""
        logger.info("Stopping connection monitoring...")

        self.is_monitoring = False

        if self.monitor_task and not self.monitor_task.done():
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass

        if self.client:
            await self.client.disconnect()

        logger.info("Success: Monitoring stopped")

    def _setup_event_handlers(self):
        """Setup event handlers for monitoring"""
        if not self.client:
            return

        # Connection events
        self.client.add_event_callback("connected", self._on_connected)
        self.client.add_event_callback("disconnected", self._on_disconnected)
        self.client.add_event_callback("reconnected", self._on_reconnected)
        self.client.add_event_callback("auth_error", self._on_auth_error)

        # Data events
        self.client.add_event_callback("balance_updated", self._on_balance_updated)
        self.client.add_event_callback("candles_received", self._on_candles_received)
        self.client.add_event_callback("message_received", self._on_message_received)

    async def _monitoring_loop(self):
        """Main monitoring loop"""
        logger.info("Persistent: Starting monitoring loop...")

        while self.is_monitoring:
            try:
                # Collect performance snapshot
                await self._collect_performance_snapshot()

                # Check connection health
                await self._check_connection_health()

                # Send ping and measure response
                await self._measure_ping_response()

                # Emit monitoring events
                await self._emit_monitoring_events()

                await asyncio.sleep(5)  # Monitor every 5 seconds

            except Exception as e:
                self.total_errors += 1
                self._record_error("monitoring_loop", str(e))
                logger.error(f"Error: Monitoring loop error: {e}")

    async def _collect_performance_snapshot(self):
        """Collect performance metrics snapshot"""
        try:
            # Try to get system metrics
            memory_mb = 0
            cpu_percent = 0

            try:
                import psutil
                import os

                process = psutil.Process(os.getpid())
                memory_mb = process.memory_info().rss / 1024 / 1024
                cpu_percent = process.cpu_percent()
            except ImportError:
                pass

            # Calculate messages per second
            uptime = (datetime.now() - self.start_time).total_seconds()
            messages_per_second = self.total_messages / uptime if uptime > 0 else 0

            # Calculate error rate
            error_rate = self.total_errors / max(self.total_messages, 1)

            # Calculate average response time
            avg_response_time = (
                statistics.mean(self.response_times) if self.response_times else 0
            )

            snapshot = PerformanceSnapshot(
                timestamp=datetime.now(),
                memory_usage_mb=memory_mb,
                cpu_percent=cpu_percent,
                active_connections=1 if self.client and self.client.is_connected else 0,
                messages_per_second=messages_per_second,
                error_rate=error_rate,
                avg_response_time=avg_response_time,
            )

            self.performance_snapshots.append(snapshot)

        except Exception as e:
            logger.error(f"Error: Error collecting performance snapshot: {e}")

    async def _check_connection_health(self):
        """Check connection health status"""
        if not self.client:
            return

        try:
            # Check if still connected
            if not self.client.is_connected:
                self._record_connection_metrics(0, "DISCONNECTED")
                return

            # Try to get balance as health check
            start_time = time.time()
            balance = await self.client.get_balance()
            response_time = time.time() - start_time

            self.response_times.append(response_time)

            if balance:
                self._record_connection_metrics(response_time, "HEALTHY")
            else:
                self._record_connection_metrics(response_time, "UNHEALTHY")

        except Exception as e:
            self.total_errors += 1
            self._record_error("health_check", str(e))
            self._record_connection_metrics(0, "ERROR")

    async def _measure_ping_response(self):
        """Measure ping response time"""
        if not self.client or not self.client.is_connected:
            return

        try:
            start_time = time.time()
            await self.client.send_message('42["ps"]')

            # Note: We can't easily measure the actual ping response time
            # since it's handled internally. This measures send time.
            ping_time = time.time() - start_time

            self.ping_times.append(ping_time)
            self.last_ping_time = datetime.now()

            self.total_messages += 1
            self.message_stats["ping"] += 1

        except Exception as e:
            self.total_errors += 1
            self._record_error("ping_measure", str(e))

    async def _emit_monitoring_events(self):
        """Emit monitoring events"""
        try:
            # Emit real-time stats
            stats = self.get_real_time_stats()
            await self._emit_event("stats_update", stats)

            # Emit alerts if needed
            await self._check_and_emit_alerts(stats)

        except Exception as e:
            logger.error(f"Error: Error emitting monitoring events: {e}")

    async def _check_and_emit_alerts(self, stats: Dict[str, Any]):
        """Check for alert conditions and emit alerts"""

        # High error rate alert
        if stats["error_rate"] > 0.1:  # 10% error rate
            await self._emit_event(
                "alert",
                {
                    "type": "high_error_rate",
                    "value": stats["error_rate"],
                    "threshold": 0.1,
                    "message": f"High error rate detected: {stats['error_rate']:.1%}",
                },
            )

        # Slow response time alert
        if stats["avg_response_time"] > 5.0:  # 5 seconds
            await self._emit_event(
                "alert",
                {
                    "type": "slow_response",
                    "value": stats["avg_response_time"],
                    "threshold": 5.0,
                    "message": f"Slow response time: {stats['avg_response_time']:.2f}s",
                },
            )

        # Connection issues alert
        if not stats["is_connected"]:
            await self._emit_event(
                "alert", {"type": "connection_lost", "message": "Connection lost"}
            )

        # Memory usage alert (if available)
        if "memory_usage_mb" in stats and stats["memory_usage_mb"] > 500:  # 500MB
            await self._emit_event(
                "alert",
                {
                    "type": "high_memory",
                    "value": stats["memory_usage_mb"],
                    "threshold": 500,
                    "message": f"High memory usage: {stats['memory_usage_mb']:.1f}MB",
                },
            )

    def _record_connection_metrics(self, connection_time: float, status: str):
        """Record connection metrics"""
        region = "UNKNOWN"
        if self.client and self.client.connection_info:
            region = self.client.connection_info.region or "UNKNOWN"

        metrics = ConnectionMetrics(
            timestamp=datetime.now(),
            connection_time=connection_time,
            ping_time=self.ping_times[-1] if self.ping_times else None,
            message_count=self.total_messages,
            error_count=self.total_errors,
            region=region,
            status=status,
        )

        self.connection_metrics.append(metrics)

    def _record_error(self, error_type: str, error_message: str):
        """Record error for analysis"""
        error_record = {
            "timestamp": datetime.now(),
            "type": error_type,
            "message": error_message,
        }
        self.error_log.append(error_record)

    async def _emit_event(self, event_type: str, data: Any):
        """Emit event to registered handlers"""
        if event_type in self.event_handlers:
            for handler in self.event_handlers[event_type]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(data)
                    else:
                        handler(data)
                except Exception as e:
                    logger.error(f"Error: Error in event handler for {event_type}: {e}")

    # Event handler methods
    async def _on_connected(self, data):
        self.total_messages += 1
        self.message_stats["connected"] += 1
        logger.info("Connection established")

    async def _on_disconnected(self, data):
        self.total_messages += 1
        self.message_stats["disconnected"] += 1
        logger.warning("Connection lost")

    async def _on_reconnected(self, data):
        self.total_messages += 1
        self.message_stats["reconnected"] += 1
        logger.info("Connection restored")

    async def _on_auth_error(self, data):
        self.total_errors += 1
        self.message_stats["auth_error"] += 1
        self._record_error("auth_error", str(data))
        logger.error("Authentication error")

    async def _on_balance_updated(self, data):
        self.total_messages += 1
        self.message_stats["balance"] += 1

    async def _on_candles_received(self, data):
        self.total_messages += 1
        self.message_stats["candles"] += 1

    async def _on_message_received(self, data):
        self.total_messages += 1
        self.message_stats["message"] += 1

    def add_event_handler(self, event_type: str, handler: Callable):
        """Add event handler for monitoring events"""
        self.event_handlers[event_type].append(handler)

    def get_real_time_stats(self) -> Dict[str, Any]:
        """Get current real-time statistics"""
        uptime = datetime.now() - self.start_time

        stats = {
            "uptime": uptime.total_seconds(),
            "uptime_str": str(uptime).split(".")[0],
            "total_messages": self.total_messages,
            "total_errors": self.total_errors,
            "error_rate": self.total_errors / max(self.total_messages, 1),
            "messages_per_second": self.total_messages / uptime.total_seconds()
            if uptime.total_seconds() > 0
            else 0,
            "connection_attempts": self.connection_attempts,
            "successful_connections": self.successful_connections,
            "connection_success_rate": self.successful_connections
            / max(self.connection_attempts, 1),
            "is_connected": self.client.is_connected if self.client else False,
            "last_ping_time": self.last_ping_time.isoformat()
            if self.last_ping_time
            else None,
            "message_types": dict(self.message_stats),
        }

        # Add response time stats
        if self.response_times:
            stats.update(
                {
                    "avg_response_time": statistics.mean(self.response_times),
                    "min_response_time": min(self.response_times),
                    "max_response_time": max(self.response_times),
                    "median_response_time": statistics.median(self.response_times),
                }
            )

        # Add ping stats
        if self.ping_times:
            stats.update(
                {
                    "avg_ping_time": statistics.mean(self.ping_times),
                    "min_ping_time": min(self.ping_times),
                    "max_ping_time": max(self.ping_times),
                }
            )

        # Add latest performance snapshot data
        if self.performance_snapshots:
            latest = self.performance_snapshots[-1]
            stats.update(
                {
                    "memory_usage_mb": latest.memory_usage_mb,
                    "cpu_percent": latest.cpu_percent,
                }
            )

        return stats

    def get_historical_metrics(self, hours: int = 1) -> Dict[str, Any]:
        """Get historical metrics for the specified time period"""
        cutoff_time = datetime.now() - timedelta(hours=hours)

        # Filter metrics
        recent_metrics = [
            m for m in self.connection_metrics if m.timestamp > cutoff_time
        ]
        recent_snapshots = [
            s for s in self.performance_snapshots if s.timestamp > cutoff_time
        ]
        recent_errors = [e for e in self.error_log if e["timestamp"] > cutoff_time]

        historical = {
            "time_period_hours": hours,
            "connection_metrics_count": len(recent_metrics),
            "performance_snapshots_count": len(recent_snapshots),
            "error_count": len(recent_errors),
            "metrics": [asdict(m) for m in recent_metrics],
            "snapshots": [asdict(s) for s in recent_snapshots],
            "errors": recent_errors,
        }

        # Calculate trends
        if recent_snapshots:
            memory_values = [
                s.memory_usage_mb for s in recent_snapshots if s.memory_usage_mb > 0
            ]
            response_values = [
                s.avg_response_time for s in recent_snapshots if s.avg_response_time > 0
            ]

            if memory_values:
                historical["memory_trend"] = {
                    "avg": statistics.mean(memory_values),
                    "min": min(memory_values),
                    "max": max(memory_values),
                    "trend": "increasing"
                    if len(memory_values) > 1 and memory_values[-1] > memory_values[0]
                    else "stable",
                }

            if response_values:
                historical["response_time_trend"] = {
                    "avg": statistics.mean(response_values),
                    "min": min(response_values),
                    "max": max(response_values),
                    "trend": "improving"
                    if len(response_values) > 1
                    and response_values[-1] < response_values[0]
                    else "stable",
                }

        return historical

    def generate_diagnostics_report(self) -> Dict[str, Any]:
        """Generate comprehensive diagnostics report"""
        stats = self.get_real_time_stats()
        historical = self.get_historical_metrics(hours=2)

        # Health assessment
        health_score = 100
        health_issues = []

        if stats["error_rate"] > 0.05:
            health_score -= 20
            health_issues.append(f"High error rate: {stats['error_rate']:.1%}")

        if not stats["is_connected"]:
            health_score -= 30
            health_issues.append("Not connected")

        if stats.get("avg_response_time", 0) > 3.0:
            health_score -= 15
            health_issues.append(
                f"Slow response time: {stats.get('avg_response_time', 0):.2f}s"
            )

        if stats["connection_success_rate"] < 0.9:
            health_score -= 10
            health_issues.append(
                f"Low connection success rate: {stats['connection_success_rate']:.1%}"
            )

        health_score = max(0, health_score)

        # Recommendations
        recommendations = []

        if stats["error_rate"] > 0.1:
            recommendations.append(
                "High error rate detected. Check network connectivity and SSID validity."
            )

        if stats.get("avg_response_time", 0) > 5.0:
            recommendations.append(
                "Slow response times. Consider using persistent connections or different region."
            )

        if stats.get("memory_usage_mb", 0) > 300:
            recommendations.append(
                "High memory usage detected. Monitor for memory leaks."
            )

        if not recommendations:
            recommendations.append("System is operating normally.")

        report = {
            "timestamp": datetime.now().isoformat(),
            "health_score": health_score,
            "health_status": "EXCELLENT"
            if health_score > 90
            else "GOOD"
            if health_score > 70
            else "FAIR"
            if health_score > 50
            else "POOR",
            "health_issues": health_issues,
            "recommendations": recommendations,
            "real_time_stats": stats,
            "historical_metrics": historical,
            "connection_summary": {
                "total_attempts": stats["connection_attempts"],
                "successful_connections": stats["successful_connections"],
                "current_status": "CONNECTED"
                if stats["is_connected"]
                else "DISCONNECTED",
                "uptime": stats["uptime_str"],
            },
        }

        return report

    def export_metrics_csv(self, filename: str = "") -> str:
        """Export metrics to CSV file"""
        if not filename:
            filename = f"metrics_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        try:
            import pandas as pd

            # Convert metrics to DataFrame
            metrics_data = []
            for metric in self.connection_metrics:
                metrics_data.append(asdict(metric))

            if metrics_data:
                df = pd.DataFrame(metrics_data)
                df.to_csv(filename, index=False)
                logger.info(f"Statistics: Metrics exported to {filename}")
            else:
                logger.warning("No metrics data to export")

            return filename

        except ImportError:
            logger.error("pandas not available for CSV export")

            # Fallback: basic CSV export
            import csv

            with open(filename, "w", newline="") as csvfile:
                if self.connection_metrics:
                    fieldnames = asdict(self.connection_metrics[0]).keys()
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    for metric in self.connection_metrics:
                        writer.writerow(asdict(metric))

            return filename


class RealTimeDisplay:
    """Real-time console display for monitoring"""

    def __init__(self, monitor: ConnectionMonitor):
        self.monitor = monitor
        self.display_task: Optional[asyncio.Task] = None
        self.is_displaying = False

    async def start_display(self):
        """Start real-time display"""
        self.is_displaying = True
        self.display_task = asyncio.create_task(self._display_loop())

    async def stop_display(self):
        """Stop real-time display"""
        self.is_displaying = False
        if self.display_task and not self.display_task.done():
            self.display_task.cancel()
            try:
                await self.display_task
            except asyncio.CancelledError:
                pass

    async def _display_loop(self):
        """Display loop"""
        while self.is_displaying:
            try:
                # Clear screen (ANSI escape sequence)
                print("\033[2J\033[H", end="")

                # Display header
                print("Analysis: PocketOption API Connection Monitor")
                print("=" * 60)

                # Get stats
                stats = self.monitor.get_real_time_stats()

                # Display connection status
                status = "Connected" if stats["is_connected"] else "Disconnected"
                print(f"Status: {status}")
                print(f"Uptime: {stats['uptime_str']}")
                print()

                # Display metrics
                print("Statistics: Metrics:")
                print(f"  Messages: {stats['total_messages']}")
                print(f"  Errors: {stats['total_errors']}")
                print(f"  Error Rate: {stats['error_rate']:.1%}")
                print(f"  Messages/sec: {stats['messages_per_second']:.2f}")
                print()

                # Display performance
                if "avg_response_time" in stats:
                    print("Performance:")
                    print(f"  Avg Response: {stats['avg_response_time']:.3f}s")
                    print(f"  Min Response: {stats['min_response_time']:.3f}s")
                    print(f"  Max Response: {stats['max_response_time']:.3f}s")
                    print()

                # Display memory if available
                if "memory_usage_mb" in stats:
                    print("Resources:")
                    print(f"  Memory: {stats['memory_usage_mb']:.1f} MB")
                    print(f"  CPU: {stats['cpu_percent']:.1f}%")
                    print()

                # Display message types
                if stats["message_types"]:
                    print("Message: Message Types:")
                    for msg_type, count in stats["message_types"].items():
                        print(f"  {msg_type}: {count}")
                    print()

                print("Press Ctrl+C to stop monitoring...")

                await asyncio.sleep(2)  # Update every 2 seconds

            except Exception as e:
                logger.error(f"Display error: {e}")
                await asyncio.sleep(1)


async def run_monitoring_demo(ssid: Optional[str] = None):
    """Run monitoring demonstration"""

    if not ssid:
        ssid = r'42["auth",{"session":"demo_session_for_monitoring","isDemo":1,"uid":0,"platform":1}]'
        logger.warning("Caution: Using demo SSID for monitoring")

    logger.info("Analysis: Starting Advanced Connection Monitor Demo")

    # Create monitor
    monitor = ConnectionMonitor(ssid, is_demo=True)

    # Add event handlers for alerts
    async def on_alert(alert_data):
        logger.warning(f"Alert: ALERT: {alert_data['message']}")

    async def on_stats_update(stats):
        # Could send to external monitoring system
        pass

    monitor.add_event_handler("alert", on_alert)
    monitor.add_event_handler("stats_update", on_stats_update)

    # Create real-time display
    display = RealTimeDisplay(monitor)

    try:
        # Start monitoring
        success = await monitor.start_monitoring(persistent_connection=True)

        if success:
            # Start real-time display
            await display.start_display()

            # Let it run for a while
            await asyncio.sleep(120)  # Run for 2 minutes

        else:
            logger.error("Error: Failed to start monitoring")

    except KeyboardInterrupt:
        logger.info("Stopping: Monitoring stopped by user")

    finally:
        # Stop display and monitoring
        await display.stop_display()
        await monitor.stop_monitoring()

        # Generate final report
        report = monitor.generate_diagnostics_report()

        logger.info("\nCompleted: FINAL DIAGNOSTICS REPORT")
        logger.info("=" * 50)
        logger.info(
            f"Health Score: {report['health_score']}/100 ({report['health_status']})"
        )

        if report["health_issues"]:
            logger.warning("Issues found:")
            for issue in report["health_issues"]:
                logger.warning(f"  - {issue}")

        logger.info("Recommendations:")
        for rec in report["recommendations"]:
            logger.info(f"  - {rec}")

        # Save detailed report
        report_file = (
            f"monitoring_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"Report: Detailed report saved to: {report_file}")

        # Export metrics
        metrics_file = monitor.export_metrics_csv()
        logger.info(f"Statistics: Metrics exported to: {metrics_file}")


if __name__ == "__main__":
    import sys

    # Allow passing SSID as command line argument
    ssid = None
    if len(sys.argv) > 1:
        ssid = sys.argv[1]
        logger.info(f"Using provided SSID: {ssid[:50]}...")

    asyncio.run(run_monitoring_demo(ssid))
