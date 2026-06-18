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
from src.auth.callback_auth import generate_callback_token

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
            cmd = [
                "docker",
                "inspect",
                "-f",
                "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                "sandbox-server-api",
            ]
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

    async def create_sandbox_container(
        self,
        sandbox_id: str,
        use_gpu: bool = False,
        sandbox_type: str = "terminal",
    ) -> Dict[str, str]:
        """
        Create a new Docker container for sandbox.

        Args:
            sandbox_id: Unique identifier for the sandbox
            use_gpu: Ignored for Docker (GPU only supported on GKE Autopilot)
        """
        # Note: use_gpu is ignored for Docker containers
        # Check container limit
        active_count = await self.count_active_containers()
        if active_count >= settings.MAX_CONTAINERS_PER_SERVER:
            raise Exception(
                f"Max container limit reached ({settings.MAX_CONTAINERS_PER_SERVER})"
            )

        container_name = f"sandbox-{sandbox_id}"

        # Select image
        image = settings.SANDBOX_BASE_IMAGE
        if sandbox_type == "jupyterlite":
            image = settings.JUPYTERLITE_IMAGE

        # Dynamically resolve IPs
        api_ip = self._get_api_server_ip()
        lt_host = urlparse(settings.LOCALTUNNEL_HOST).hostname
        lt_ip = self._get_host_ip(settings.LOCALTUNNEL_HOST)

        # Create custom resolv.conf for gVisor to bypass Docker DNS (127.0.0.11)
        host_resolv_path = None
        if settings.USE_GVISOR:
            resolv_filename = f"resolv-{sandbox_id}.conf"
            container_resolv_path = (
                f"{settings.RESOLV_CONF_CONTAINER_DIR}/{resolv_filename}"
            )
            host_resolv_path = f"{settings.RESOLV_CONF_HOST_DIR}/{resolv_filename}"

            try:
                with open(container_resolv_path, "w") as f:
                    f.write("nameserver 8.8.8.8\n")
                    f.write("nameserver 8.8.4.4\n")
                    f.write("options ndots:0\n")
                logger.info(
                    f"Created custom resolv.conf for gVisor container {sandbox_id}"
                )
            except Exception as e:
                logger.warning(f"Failed to create custom resolv.conf: {e}")
                host_resolv_path = None

        # Generate callback token for this sandbox
        callback_token = generate_callback_token(sandbox_id)

        try:
            # Build docker run command with port mapping
            cmd = [
                "docker",
                "run",
                "-d",
            ]

            # Add gVisor runtime if enabled
            if settings.USE_GVISOR:
                cmd.extend(["--runtime=runsc"])
                logger.info(f"Using gVisor runtime for container {sandbox_id}")
            else:
                logger.info(f"Using default runtime for container {sandbox_id}")

            cmd.extend(
                [
                    "--name",
                    container_name,
                    "--network",
                    settings.DOCKER_NETWORK,
                    "--memory",
                    settings.CONTAINER_MEMORY_LIMIT,
                    "--cpus",
                    str(settings.CONTAINER_CPU_LIMIT),
                    "-p",
                    "0:8888",
                ]
            )

            # Mount custom resolv.conf to bypass Docker DNS (required for gVisor)
            if host_resolv_path:
                cmd.extend(["-v", f"{host_resolv_path}:/etc/resolv.conf:ro"])
            else:
                cmd.extend(["--dns", "8.8.8.8", "--dns", "8.8.4.4"])

            cmd.extend(
                [
                    "--add-host",
                    f"api-server:{api_ip}",
                ]
            )

            # Add localtunnel host mapping if resolved
            if lt_host and lt_ip:
                cmd.extend(["--add-host", f"{lt_host}:{lt_ip}"])

            cmd.extend(
                [
                    "-e",
                    f"TERMINAL_ID={sandbox_id}",
                    "-e",
                    f"API_CALLBACK_URL={settings.API_BASE_URL}/api/v1/callbacks",
                    "-e",
                    f"CALLBACK_TOKEN={callback_token}",
                    "-e",
                    f"LOCALTUNNEL_HOST={settings.LOCALTUNNEL_HOST}",
                    "-e",
                    f"TERMINAL_IDLE_TIMEOUT_SECONDS={settings.SANDBOX_IDLE_TIMEOUT_SECONDS}",
                    "-e",
                    f"SANDBOX_TYPE={sandbox_type}",
                    "--label",
                    "app=sandbox-server",
                    "--label",
                    f"sandbox_id={sandbox_id}",
                    "--label",
                    f"sandbox_type={sandbox_type}",
                    image,
                ]
            )

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
                    port_output = port_result.stdout.strip()
                    if ":" in port_output:
                        host_port = port_output.split(":")[-1]

                logger.info(
                    f"Created Docker container: {container_id} for sandbox {sandbox_id}, host port: {host_port}"
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
                f"Failed to create Docker container for sandbox {sandbox_id}: {e}"
            )
            raise

    async def delete_sandbox_container(self, container_id: str) -> bool:
        """Delete a Docker container"""
        try:
            # Get sandbox_id from container name to clean up resolv.conf (if using gVisor)
            if settings.USE_GVISOR:
                inspect_result = subprocess.run(
                    ["docker", "inspect", "--format", "{{.Name}}", container_id],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if inspect_result.returncode == 0:
                    container_name = inspect_result.stdout.strip().lstrip("/")
                    if container_name.startswith("sandbox-"):
                        sandbox_id = container_name.replace("sandbox-", "")
                        container_resolv_path = f"{settings.RESOLV_CONF_CONTAINER_DIR}/resolv-{sandbox_id}.conf"
                        try:
                            if os.path.exists(container_resolv_path):
                                os.remove(container_resolv_path)
                                logger.info(f"Cleaned up resolv.conf for {sandbox_id}")
                        except Exception as e:
                            logger.warning(f"Failed to cleanup resolv.conf: {e}")

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

    async def stop_sandbox_container(self, container_id: str) -> bool:
        """Stop a Docker container for idle timeout"""
        try:
            # Get sandbox_id from container name to clean up resolv.conf (if using gVisor)
            if settings.USE_GVISOR:
                inspect_result = subprocess.run(
                    ["docker", "inspect", "--format", "{{.Name}}", container_id],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if inspect_result.returncode == 0:
                    container_name = inspect_result.stdout.strip().lstrip("/")
                    if container_name.startswith("sandbox-"):
                        sandbox_id = container_name.replace("sandbox-", "")
                        container_resolv_path = f"{settings.RESOLV_CONF_CONTAINER_DIR}/resolv-{sandbox_id}.conf"
                        try:
                            if os.path.exists(container_resolv_path):
                                os.remove(container_resolv_path)
                                logger.info(f"Cleaned up resolv.conf for {sandbox_id}")
                        except Exception as e:
                            logger.warning(f"Failed to cleanup resolv.conf: {e}")

            # Stop container
            subprocess.run(
                ["docker", "stop", "--time=10", container_id],
                capture_output=True,
                timeout=15,
            )

            # Remove container
            result = subprocess.run(
                ["docker", "rm", container_id], capture_output=True, timeout=10
            )

            if result.returncode == 0:
                logger.info(
                    f"Stopped Docker container for idle timeout: {container_id}"
                )
                return True
            else:
                logger.error(
                    f"Failed to stop container {container_id}: {result.stderr.decode()}"
                )
                return False

        except Exception as e:
            logger.error(f"Failed to stop Docker container {container_id}: {e}")
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

    async def get_container_ip(self, container_id: str) -> Optional[str]:
        """Get Docker container IP"""
        try:
            cmd = [
                "docker",
                "inspect",
                "-f",
                "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                container_id,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            return None
        except Exception as e:
            logger.error(f"Failed to get IP for container {container_id}: {e}")
            return None

    async def count_active_containers(self) -> int:
        """Count number of active sandbox containers"""
        try:
            # Count containers with label app=sandbox-server
            cmd = [
                "docker",
                "ps",
                "--filter",
                "label=app=sandbox-server",
                "--filter",
                "status=running",
                "--format",
                "{{.ID}}",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

            if result.returncode == 0:
                output = result.stdout.strip()
                if not output:
                    return 0
                return len(output.split("\n"))
            else:
                logger.error(f"Failed to count containers: {result.stderr}")
                return 0

        except Exception as e:
            logger.error(f"Failed to count active containers: {e}")
            return 0

    async def get_container_stats(self, container_id: str) -> Optional[Dict]:
        """Get container resource usage statistics"""
        try:
            cmd = [
                "docker",
                "stats",
                container_id,
                "--no-stream",
                "--format",
                "{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}}",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(",")
                if len(parts) >= 3:
                    cpu_str = parts[0].strip().replace("%", "")
                    mem_usage_str = parts[1].strip().split("/")[0].strip()
                    mem_perc_str = parts[2].strip().replace("%", "")

                    def parse_memory(mem_str):
                        mem_str = mem_str.upper()
                        if "GIB" in mem_str or "GB" in mem_str:
                            return (
                                float(mem_str.replace("GIB", "").replace("GB", ""))
                                * 1024
                            )
                        elif "MIB" in mem_str or "MB" in mem_str:
                            return float(mem_str.replace("MIB", "").replace("MB", ""))
                        elif "KIB" in mem_str or "KB" in mem_str:
                            return (
                                float(mem_str.replace("KIB", "").replace("KB", ""))
                                / 1024
                            )
                        elif "B" in mem_str:
                            return float(mem_str.replace("B", "")) / (1024 * 1024)
                        return 0.0

                    try:
                        cpu_percent = float(cpu_str)
                        memory_mb = parse_memory(mem_usage_str)
                        memory_percent = float(mem_perc_str)

                        return {
                            "cpu_percent": cpu_percent,
                            "memory_mb": memory_mb,
                            "memory_percent": memory_percent,
                        }
                    except ValueError:
                        pass

            return None

        except Exception as e:
            logger.error(f"Failed to get stats for container {container_id}: {e}")
            return None
