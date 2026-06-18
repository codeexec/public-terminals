import tornado.ioloop
import tornado.web
import logging
import json
import os
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global state for tunnel URL
status_info = {
    "tunnel_url": None,
    "status": "starting",
    "sandbox_id": os.environ.get("TERMINAL_ID", "unknown"),
    "sandbox_type": "jupyterlite",
    "started_at": datetime.now(timezone.utc).isoformat(),
}


class HealthHandler(tornado.web.RequestHandler):
    """Health check endpoint"""

    def get(self):
        self.set_header("Content-Type", "application/json")
        self.write(
            json.dumps(
                {
                    "status": "healthy",
                    "sandbox_id": status_info["sandbox_id"],
                    "sandbox_type": status_info["sandbox_type"],
                    "uptime": (
                        datetime.now(timezone.utc)
                        - datetime.fromisoformat(str(status_info["started_at"]))
                    ).seconds,
                }
            )
        )


class StatusHandler(tornado.web.RequestHandler):
    """Status endpoint with tunnel URL"""

    def get(self):
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(status_info))

    def post(self):
        """Allow updating tunnel info"""
        try:
            data = json.loads(self.request.body)
            if "tunnel_url" in data:
                status_info["tunnel_url"] = data["tunnel_url"]
                status_info["status"] = "ready"
                logger.info(f"Tunnel URL updated: {data['tunnel_url']}")
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps({"success": True}))
        except Exception as e:
            logger.error(f"Error updating status: {e}")
            self.set_status(400)
            self.write(json.dumps({"error": str(e)}))


# Tornado application
def make_app():
    return tornado.web.Application(
        [
            (r"/health", HealthHandler),
            (r"/status", StatusHandler),
            (
                r"/(.*)",
                tornado.web.StaticFileHandler,
                {"path": "/app/dist", "default_filename": "index.html"},
            ),
        ]
    )


if __name__ == "__main__":
    port = 8888
    logger.info(f"Starting JupyterLite static server on port {port}")
    app = make_app()
    app.listen(port)
    tornado.ioloop.IOLoop.current().start()
