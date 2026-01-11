from unittest.mock import MagicMock, patch, mock_open
import sys
import os

# Add parent directory to path to import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from stats_reporter import collect_stats, send_stats


class TestStatsReporter:
    @patch("psutil.cpu_percent")
    @patch("psutil.virtual_memory")
    @patch("builtins.open", new_callable=mock_open)
    @patch("os.path.exists")
    def test_collect_stats_cgroup_v2(
        self, mock_exists, mock_file, mock_virtual_memory, mock_cpu_percent
    ):
        """Test stats collection using Cgroup V2."""
        mock_cpu_percent.return_value = 15.5

        # Mock Cgroup V2 files existing
        def exists_side_effect(path):
            return path in [
                "/sys/fs/cgroup/memory.current",
                "/sys/fs/cgroup/memory.max",
            ]

        mock_exists.side_effect = exists_side_effect

        # Mock file content
        def open_side_effect(file, mode="r"):
            if file == "/sys/fs/cgroup/memory.current":
                f = mock_open(read_data="104857600").return_value  # 100 MB
                f.__enter__.return_value.read.return_value = "104857600"
                return f
            if file == "/sys/fs/cgroup/memory.max":
                f = mock_open(read_data="209715200").return_value  # 200 MB
                f.__enter__.return_value.read.return_value = "209715200"
                return f
            raise FileNotFoundError(file)

        mock_file.side_effect = open_side_effect

        # Limit fallback needs mock (though not used if file read succeeds)
        mock_mem_host = MagicMock()
        mock_mem_host.total = 1000000000
        mock_virtual_memory.return_value = mock_mem_host

        stats = collect_stats()

        assert stats is not None
        assert stats["cpu_percent"] == 15.5
        assert stats["memory_mb"] == 100.0
        assert stats["memory_percent"] == 50.0

    @patch("psutil.cpu_percent")
    @patch("psutil.virtual_memory")
    @patch("psutil.process_iter")
    @patch("os.path.exists")
    def test_collect_stats_fallback(
        self, mock_exists, mock_process_iter, mock_virtual_memory, mock_cpu_percent
    ):
        """Test stats collection falling back to process iteration."""
        mock_cpu_percent.return_value = 15.5
        mock_exists.return_value = False  # No cgroups

        # Mock process rss
        p1 = MagicMock()
        p1.info = {"memory_info": MagicMock(rss=52428800)}  # 50 MB
        p2 = MagicMock()
        p2.info = {"memory_info": MagicMock(rss=52428800)}  # 50 MB
        mock_process_iter.return_value = [p1, p2]

        # Host memory for limit (since cgroup limit failed)
        mock_mem_host = MagicMock()
        mock_mem_host.total = 209715200  # 200 MB
        mock_virtual_memory.return_value = mock_mem_host

        stats = collect_stats()

        assert stats is not None
        assert stats["memory_mb"] == 100.0  # 50 + 50
        assert stats["memory_percent"] == 50.0  # 100 / 200 * 100

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
