#!/usr/bin/env python3
"""
Stats Reporter - Collects and sends container resource statistics to API
Runs in background and reports CPU and memory usage every 30 seconds
"""

import os
import sys
import time
import logging
import psutil
import httpx

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)


def collect_stats():
    """Collect CPU and memory statistics"""
    try:
        # Get CPU usage (percentage)
        # Note: psutil.cpu_percent in a container returns host CPU usage by default
        # Ideally we should use cgroups for this too, but for now we'll stick to psutil
        # as it's less critical than the memory reporting error.
        cpu_percent = psutil.cpu_percent(interval=1)

        # Get memory usage
        # psutil.virtual_memory() returns HOST memory in Docker.
        # We need to read cgroups or sum process memory.
        memory_usage_bytes = 0
        memory_limit_bytes = 0

        try:
            # 1. Try Cgroup V2
            if os.path.exists("/sys/fs/cgroup/memory.current"):
                with open("/sys/fs/cgroup/memory.current", "r") as f:
                    memory_usage_bytes = int(f.read().strip())

                with open("/sys/fs/cgroup/memory.max", "r") as f:
                    val = f.read().strip()
                    if val != "max":
                        memory_limit_bytes = int(val)

            # 2. Fallback: Sum of Process RSS
            else:
                for p in psutil.process_iter(["memory_info"]):
                    try:
                        memory_usage_bytes += p.info["memory_info"].rss
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

        except Exception as e:
            logger.warning(f"Error reading memory stats: {e}")
            # If cgroup read failed, try process sum
            if memory_usage_bytes == 0:
                for p in psutil.process_iter(["memory_info"]):
                    try:
                        memory_usage_bytes += p.info["memory_info"].rss
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

        # Validate Limit
        host_mem = psutil.virtual_memory()
        if memory_limit_bytes == 0 or memory_limit_bytes > host_mem.total:
            memory_limit_bytes = host_mem.total

        memory_mb = memory_usage_bytes / (1024 * 1024)
        memory_percent = (
            (memory_usage_bytes / memory_limit_bytes) * 100
            if memory_limit_bytes > 0
            else 0
        )

        return {
            "cpu_percent": round(cpu_percent, 2),
            "memory_mb": round(memory_mb, 2),
            "memory_percent": round(memory_percent, 2),
        }
    except Exception as e:
        logger.error(f"Failed to collect stats: {e}")
        return None


def send_stats(terminal_id, stats, api_callback_url):
    """Send statistics to API callback endpoint"""
    try:
        url = f"{api_callback_url}/stats"
        payload = {
            "terminal_id": terminal_id,
            "cpu_percent": stats["cpu_percent"],
            "memory_mb": stats["memory_mb"],
            "memory_percent": stats["memory_percent"],
        }

        with httpx.Client(timeout=5.0) as client:
            response = client.post(url, json=payload)

            if response.status_code == 200:
                logger.debug(
                    f"Stats sent successfully: CPU={stats['cpu_percent']}%, "
                    f"MEM={stats['memory_mb']}MB"
                )
                return True
            else:
                logger.warning(f"Failed to send stats: HTTP {response.status_code}")
                return False

    except Exception as e:
        logger.error(f"Error sending stats: {e}")
        return False


def main():
    """Main loop - collect and send stats every 30 seconds"""
    terminal_id = os.environ.get("TERMINAL_ID")
    api_callback_url = os.environ.get("API_CALLBACK_URL")

    if not terminal_id or not api_callback_url:
        logger.error("Missing TERMINAL_ID or API_CALLBACK_URL environment variables")
        sys.exit(1)

    logger.info(f"Stats reporter started for terminal {terminal_id}")
    logger.info(f"Reporting to: {api_callback_url}/stats")

    # Wait a bit before starting to let container fully initialize
    time.sleep(10)

    while True:
        try:
            stats = collect_stats()

            if stats:
                send_stats(terminal_id, stats, api_callback_url)

            # Wait 30 seconds before next report
            time.sleep(30)

        except KeyboardInterrupt:
            logger.info("Stats reporter stopped")
            break
        except Exception as e:
            logger.error(f"Unexpected error in stats loop: {e}")
            time.sleep(30)  # Continue after error


if __name__ == "__main__":
    main()
