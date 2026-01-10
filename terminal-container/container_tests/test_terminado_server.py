from unittest.mock import MagicMock
import sys
import os
import json
import tornado.web
import tornado.testing

# Add parent directory to path to import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Mock terminado before importing the server to avoid PTY creation
mock_terminado = MagicMock()
sys.modules["terminado"] = mock_terminado

# Now import the server module
from terminado_server import HealthHandler, StatusHandler, tunnel_info  # noqa: E402


class TestTerminadoServer(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        return tornado.web.Application(
            [
                (r"/health", HealthHandler),
                (r"/status", StatusHandler),
            ]
        )

    def setUp(self):
        super().setUp()
        # Reset global state for each test
        tunnel_info["tunnel_url"] = None
        tunnel_info["status"] = "starting"

    def test_health_check(self):
        """Test health check endpoint returns healthy status."""
        response = self.fetch("/health")
        assert response.code == 200
        data = json.loads(response.body)
        assert data["status"] == "healthy"
        assert "uptime" in data

    def test_get_status(self):
        """Test status endpoint returns current tunnel info."""
        response = self.fetch("/status")
        assert response.code == 200
        data = json.loads(response.body)
        assert data["status"] == "starting"
        assert data["tunnel_url"] is None

    def test_update_status(self):
        """Test updating tunnel URL via POST to status endpoint."""
        payload = {"tunnel_url": "https://test.tunnel.com"}
        response = self.fetch("/status", method="POST", body=json.dumps(payload))
        assert response.code == 200

        # Verify state updated in global dictionary
        assert tunnel_info["tunnel_url"] == "https://test.tunnel.com"
        assert tunnel_info["status"] == "ready"

        # Verify subsequent GET returns new state
        response = self.fetch("/status")
        data = json.loads(response.body)
        assert data["tunnel_url"] == "https://test.tunnel.com"

    def test_update_status_invalid_json(self):
        """Test error handling for invalid JSON in POST request."""
        response = self.fetch("/status", method="POST", body="invalid json")
        assert response.code == 400
