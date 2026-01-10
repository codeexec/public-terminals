#!/usr/bin/env python3
"""
Idle Monitor - Detects terminal inactivity and reports to API for shutdown
Monitors both user connections and command execution activity
"""

import os
import sys
import time
import logging
import httpx
import psutil
from datetime import datetime

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)


class IdleMonitor:
    def __init__(
        self,
        terminal_id: str,
        api_callback_url: str,
        idle_timeout_seconds: int,
        check_interval_seconds: int = 60,
    ):
        self.terminal_id = terminal_id
        self.api_callback_url = api_callback_url
        self.idle_timeout_seconds = idle_timeout_seconds
        self.check_interval_seconds = check_interval_seconds
        self.last_activity_time = datetime.now()
        self.shutdown_reported = False

    def has_websocket_connections(self) -> bool:
        """Check if there are any active WebSocket connections on port 8888"""
        try:
            connections = psutil.net_connections(kind="inet")
            for conn in connections:
                # Check for established connections on port 8888 (Terminado server)
                if conn.status == psutil.CONN_ESTABLISHED and conn.laddr.port == 8888:
                    # Ignore localhost connections (internal infrastructure like localtunnel)
                    # Only count external connections as user activity
                    if conn.raddr and conn.raddr.ip not in ["127.0.0.1", "::1"]:
                        logger.debug(
                            f"Found external connection: {conn.raddr.ip}:{conn.raddr.port}"
                        )
                        return True
            return False
        except Exception as e:
            logger.warning(f"Failed to check WebSocket connections: {e}")
            return False

    def has_running_commands(self) -> bool:
        """Check if there are any commands running in the terminal (bash processes with children)"""
        try:
            # Look for bash processes that have child processes
            # This indicates a command is running in the terminal
            for proc in psutil.process_iter(["name", "pid", "ppid"]):
                try:
                    if proc.info["name"] == "bash":
                        # Check if this bash process has any children
                        children = proc.children(recursive=False)
                        if children:
                            # Filter out our own monitoring processes
                            non_monitor_children = [
                                child
                                for child in children
                                if child.name()
                                not in ["python", "python3", "idle_monitor.py"]
                            ]
                            if non_monitor_children:
                                logger.debug(
                                    f"Found bash process {proc.info['pid']} with running children: "
                                    f"{[c.name() for c in non_monitor_children]}"
                                )
                                return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return False
        except Exception as e:
            logger.warning(f"Failed to check running commands: {e}")
            return False

    def is_active(self) -> bool:
        """Check if terminal has any activity (connections or running commands)"""
        has_connections = self.has_websocket_connections()
        has_commands = self.has_running_commands()

        is_active = has_connections or has_commands

        logger.debug(
            f"Activity check: WebSocket connections={has_connections}, "
            f"Running commands={has_commands}, Active={is_active}"
        )

        return is_active

    def report_idle_shutdown(self) -> bool:
        """Report to API that terminal should be shut down due to inactivity"""
        try:
            url = f"{self.api_callback_url}/idle"
            idle_minutes = self.idle_timeout_seconds // 60
            payload = {
                "terminal_id": self.terminal_id,
                "idle_seconds": self.idle_timeout_seconds,
                "message": f"Terminal idle for {idle_minutes} minutes ({self.idle_timeout_seconds} seconds)",
            }

            logger.info(
                f"Reporting idle shutdown for terminal {self.terminal_id} "
                f"(idle for {idle_minutes}+ minutes / {self.idle_timeout_seconds}+ seconds)"
            )

            with httpx.Client(timeout=10.0) as client:
                response = client.post(url, json=payload)

                if response.status_code == 200:
                    logger.info("Idle shutdown reported successfully to API")
                    return True
                else:
                    logger.warning(
                        f"Failed to report idle shutdown: HTTP {response.status_code}"
                    )
                    return False

        except Exception as e:
            logger.error(f"Error reporting idle shutdown: {e}")
            return False

    def run(self):
        """Main monitoring loop"""
        timeout_minutes = self.idle_timeout_seconds // 60
        logger.info(
            f"Idle monitor started for terminal {self.terminal_id} "
            f"(timeout: {timeout_minutes} minutes / {self.idle_timeout_seconds} seconds, "
            f"check interval: {self.check_interval_seconds}s)"
        )

        # Wait a bit before starting to let container fully initialize
        time.sleep(30)

        while True:
            try:
                is_active = self.is_active()

                if is_active:
                    # Reset idle timer
                    self.last_activity_time = datetime.now()
                    self.shutdown_reported = False
                    logger.debug("Terminal is active, resetting idle timer")
                else:
                    # Check how long we've been idle
                    idle_duration = datetime.now() - self.last_activity_time
                    idle_seconds: float = idle_duration.total_seconds()
                    idle_minutes: float = idle_seconds / 60

                    logger.info(
                        f"Terminal idle for {idle_minutes:.1f} minutes ({idle_seconds:.0f} seconds) "
                        f"(threshold: {self.idle_timeout_seconds} seconds)"
                    )

                    # If we've exceeded the timeout and haven't reported yet
                    if (
                        idle_seconds >= self.idle_timeout_seconds
                        and not self.shutdown_reported
                    ):
                        logger.warning(
                            f"Terminal has been idle for {idle_minutes:.1f} minutes ({idle_seconds:.0f} seconds), "
                            f"reporting shutdown to API"
                        )
                        if self.report_idle_shutdown():
                            self.shutdown_reported = True
                            logger.info(
                                "Shutdown reported, continuing to monitor until container is stopped"
                            )

                # Wait before next check
                time.sleep(self.check_interval_seconds)

            except KeyboardInterrupt:
                logger.info("Idle monitor stopped")
                break
            except Exception as e:
                logger.error(f"Unexpected error in idle monitor loop: {e}")
                time.sleep(self.check_interval_seconds)


def main():
    """Main entry point"""
    terminal_id = os.environ.get("TERMINAL_ID")
    api_callback_url = os.environ.get("API_CALLBACK_URL")
    idle_timeout_seconds = int(os.environ.get("TERMINAL_IDLE_TIMEOUT_SECONDS", "3600"))
    check_interval_seconds = int(os.environ.get("IDLE_CHECK_INTERVAL_SECONDS", "60"))

    if not terminal_id or not api_callback_url:
        logger.error("Missing TERMINAL_ID or API_CALLBACK_URL environment variables")
        sys.exit(1)

    monitor = IdleMonitor(
        terminal_id=terminal_id,
        api_callback_url=api_callback_url,
        idle_timeout_seconds=idle_timeout_seconds,
        check_interval_seconds=check_interval_seconds,
    )

    monitor.run()


if __name__ == "__main__":
    main()
