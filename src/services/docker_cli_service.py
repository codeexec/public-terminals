"""
Docker CLI Service - Uses docker command line instead of Python SDK
This bypasses the urllib3 compatibility issues
"""

import logging
import subprocess
import socket
import os
from typing import Dict, Optional
from urllib.parse import urlparse

from src.config import settings
from src.services.interfaces import ContainerServiceInterface

logger = logging.getLogger(__name__)


class DockerCLIService(ContainerServiceInterface):
    """Docker service using CLI commands instead of Python SDK"""

    def __init__(self):
        # Test Docker CLI is available
        try:
            result = subprocess.run(
                ["docker", "version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                logger.info("Docker CLI service initialized successfully")
            else:
                raise Exception("Docker CLI not available")
        except Exception as e:
            logger.error(f"Failed to initialize Docker CLI service: {e}")
            raise

    def _get_api_server_ip(self) -> str:
        """Get the internal IP of the api-server container"""
        try:
            # Try to get it from the container name used in docker-compose
            cmd = ["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", "terminal-server-api"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            
            # Fallback: try to resolve it via DNS (if it works on host)
            return socket.gethostbyname("api-server")
        except Exception as e:
            logger.warning(f"Could not dynamically resolve api-server IP: {e}")
            return "172.18.0.5"  # Last resort fallback

    def _get_host_ip(self, url: str) -> Optional[str]:
        """Resolve a URL's hostname to an IP address"""
        try:
            hostname = urlparse(url).hostname
            if hostname:
                return socket.gethostbyname(hostname)
        except Exception as e:
            logger.warning(f"Could not resolve IP for {url}: {e}")
        return None

    async def create_terminal_container(self, terminal_id: str) -> Dict[str, str]:
        """Create a new Docker container for terminal"""
        container_name = f"terminal-{terminal_id}"
        
        # Dynamically resolve IPs
        api_ip = self._get_api_server_ip()
        lt_host = urlparse(settings.LOCALTUNNEL_HOST).hostname
        lt_ip = self._get_host_ip(settings.LOCALTUNNEL_HOST)

        try:
            # Build docker run command with port mapping
            # -p 0:8888 maps container port 8888 to a random available host port
            # --network connects to the same network as the API container
            # --runtime=runsc uses gVisor for enhanced isolation
            cmd = [
                "docker",
                "run",
                "-d",  # Detach
                "--runtime=runsc",  # Use gVisor for sandboxing
                "--name",
                container_name,
                "--network",
                settings.DOCKER_NETWORK,  # Use same network as API
                "--memory",
                "1g",
                "--cpus",
                "1",
                "-p",
                "0:8888",  # Map to random host port
                "--dns",
                "8.8.8.8",
                "--dns",
                "8.8.4.4",
                "--add-host",
                f"api-server:{api_ip}",
            ]

            # Add localtunnel host mapping if resolved
            if lt_host and lt_ip:
                cmd.extend(["--add-host", f"{lt_host}:{lt_ip}"])

            cmd.extend([
                "-e",
                f"TERMINAL_ID={terminal_id}",
                "-e",
                f"API_CALLBACK_URL={settings.API_BASE_URL}/api/v1/callbacks",
                "-e",
                f"LOCALTUNNEL_HOST={settings.LOCALTUNNEL_HOST}",
                "--label",
                "app=terminal-server",
                "--label",
                f"terminal_id={terminal_id}",
                settings.TERMINAL_IMAGE,
            ])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                container_id = result.stdout.strip()

                # Get the mapped host port
                port_result = subprocess.run(
                    ["docker", "port", container_id, "8888"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                host_port = ""
                if port_result.returncode == 0:
                    # Output format: "0.0.0.0:PORT" or "[::]:PORT"
                    port_output = port_result.stdout.strip()
                    if ":" in port_output:
                        host_port = port_output.split(":")[-1]

                logger.info(
                    f"Created Docker container: {container_id} for terminal {terminal_id}, host port: {host_port}"
                )

                return {
                    "container_id": container_id,
                    "container_name": container_name,
                    "host_port": host_port,
                }
            else:
                raise Exception(f"Docker run failed: {result.stderr}")

        except Exception as e:
            logger.error(
                f"Failed to create Docker container for terminal {terminal_id}: {e}"
            )
            raise

    async def delete_terminal_container(self, container_id: str) -> bool:
        """Delete a Docker container"""
        try:
            # Stop container
            subprocess.run(
                ["docker", "stop", container_id], capture_output=True, timeout=15
            )

            # Remove container
            result = subprocess.run(
                ["docker", "rm", container_id], capture_output=True, timeout=10
            )

            if result.returncode == 0:
                logger.info(f"Deleted Docker container: {container_id}")
                return True
            else:
                logger.error(
                    f"Failed to delete container {container_id}: {result.stderr.decode()}"
                )
                return False

        except Exception as e:
            logger.error(f"Failed to delete Docker container {container_id}: {e}")
            return False

    async def get_container_status(self, container_id: str) -> Optional[str]:
        """Get Docker container status"""
        try:
            result = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Status}}", container_id],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                return result.stdout.strip()
            else:
                return None

        except Exception as e:
            logger.error(f"Failed to get status for container {container_id}: {e}")
            return None
