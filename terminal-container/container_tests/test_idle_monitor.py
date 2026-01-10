import pytest
from unittest.mock import MagicMock, patch
import sys
import os

# Add parent directory to path to import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from idle_monitor import IdleMonitor


class TestIdleMonitor:
    @pytest.fixture
    def monitor(self):
        return IdleMonitor(
            terminal_id="test-term",
            api_callback_url="http://test-api",
            idle_timeout_seconds=3600,
            check_interval_seconds=60,
        )

    @patch("psutil.net_connections")
    def test_has_websocket_connections_true(self, mock_net_connections, monitor):
        """Test that external connections on port 8888 are detected."""
        # Mock a connection on port 8888 from external IP
        mock_conn = MagicMock()
        mock_conn.status = "ESTABLISHED"
        mock_conn.laddr.port = 8888
        mock_conn.raddr.ip = "192.168.1.100"
        mock_conn.raddr.port = 12345

        mock_net_connections.return_value = [mock_conn]

        assert monitor.has_websocket_connections() is True

    @patch("psutil.net_connections")
    def test_has_websocket_connections_false_localhost(
        self, mock_net_connections, monitor
    ):
        """Test that localhost connections are ignored."""
        # Mock a connection on port 8888 from localhost (should be ignored)
        mock_conn = MagicMock()
        mock_conn.status = "ESTABLISHED"
        mock_conn.laddr.port = 8888
        mock_conn.raddr.ip = "127.0.0.1"

        mock_net_connections.return_value = [mock_conn]

        assert monitor.has_websocket_connections() is False

    @patch("psutil.net_connections")
    def test_has_websocket_connections_false_no_port_8888(
        self, mock_net_connections, monitor
    ):
        """Test that connections on other ports are ignored."""
        # Mock connections not on port 8888
        mock_conn = MagicMock()
        mock_conn.status = "ESTABLISHED"
        mock_conn.laddr.port = 80
        mock_conn.raddr.ip = "192.168.1.100"

        mock_net_connections.return_value = [mock_conn]

        assert monitor.has_websocket_connections() is False

    @patch("psutil.process_iter")
    def test_has_running_commands_true(self, mock_process_iter, monitor):
        """Test that active bash processes with children are detected."""
        # Mock bash process with children
        mock_bash = MagicMock()
        mock_bash.info = {"name": "bash", "pid": 100, "ppid": 1}

        mock_child = MagicMock()
        mock_child.name.return_value = "ls"

        mock_bash.children.return_value = [mock_child]

        mock_process_iter.return_value = [mock_bash]

        assert monitor.has_running_commands() is True

    @patch("psutil.process_iter")
    def test_has_running_commands_false_monitor_only(self, mock_process_iter, monitor):
        """Test that monitor's own processes are ignored."""
        # Mock bash process with only python children (monitor itself)
        mock_bash = MagicMock()
        mock_bash.info = {"name": "bash", "pid": 100, "ppid": 1}

        mock_child = MagicMock()
        mock_child.name.return_value = "idle_monitor.py"

        mock_bash.children.return_value = [mock_child]

        mock_process_iter.return_value = [mock_bash]

        assert monitor.has_running_commands() is False

    @patch("httpx.Client")
    def test_report_idle_shutdown_success(self, mock_client_cls, monitor):
        """Test successful idle shutdown reporting."""
        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.post.return_value.status_code = 200

        assert monitor.report_idle_shutdown() is True
        mock_client.post.assert_called_once()

        # Verify payload
        args, kwargs = mock_client.post.call_args
        assert kwargs["json"]["terminal_id"] == "test-term"
        assert kwargs["json"]["idle_seconds"] == 3600

    @patch("httpx.Client")
    def test_report_idle_shutdown_failure(self, mock_client_cls, monitor):
        """Test handling of failed idle shutdown reporting."""
        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.post.return_value.status_code = 500

        assert monitor.report_idle_shutdown() is False
