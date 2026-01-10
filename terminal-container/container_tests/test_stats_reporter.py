from unittest.mock import MagicMock, patch
import sys
import os

# Add parent directory to path to import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from stats_reporter import collect_stats, send_stats


class TestStatsReporter:
    @patch("psutil.cpu_percent")
    @patch("psutil.virtual_memory")
    def test_collect_stats_success(self, mock_virtual_memory, mock_cpu_percent):
        """Test successful collection of system statistics."""
        mock_cpu_percent.return_value = 15.5

        mock_mem = MagicMock()
        mock_mem.used = 104857600  # 100 MB
        mock_mem.percent = 45.0
        mock_virtual_memory.return_value = mock_mem

        stats = collect_stats()

        assert stats is not None
        assert stats["cpu_percent"] == 15.5
        assert stats["memory_mb"] == 100.0
        assert stats["memory_percent"] == 45.0

    @patch("psutil.cpu_percent")
    def test_collect_stats_failure(self, mock_cpu_percent):
        """Test handling of errors during stats collection."""
        mock_cpu_percent.side_effect = Exception("Test error")

        stats = collect_stats()

        assert stats is None

    @patch("httpx.Client")
    def test_send_stats_success(self, mock_client_cls):
        """Test successful sending of stats to API."""
        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.post.return_value.status_code = 200

        stats = {"cpu_percent": 10.0, "memory_mb": 100.0, "memory_percent": 50.0}

        assert send_stats("test-term", stats, "http://test-api") is True

        args, kwargs = mock_client.post.call_args
        assert kwargs["json"]["terminal_id"] == "test-term"
        assert kwargs["json"]["cpu_percent"] == 10.0

    @patch("httpx.Client")
    def test_send_stats_failure(self, mock_client_cls):
        """Test handling of failed stats reporting."""
        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.post.return_value.status_code = 500

        stats = {"cpu_percent": 10.0, "memory_mb": 100.0, "memory_percent": 50.0}

        assert send_stats("test-term", stats, "http://test-api") is False
