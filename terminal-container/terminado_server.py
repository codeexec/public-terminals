import tornado.ioloop
import tornado.web
from terminado import TermSocket, SingleTermManager
import logging
import json
import os
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Terminal manager
term_manager = SingleTermManager(shell_command=["bash"])

# Global state for tunnel URL
tunnel_info = {
    "tunnel_url": None,
    "status": "starting",
    "terminal_id": os.environ.get("TERMINAL_ID", "unknown"),
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
                    "terminal_id": tunnel_info["terminal_id"],
                    "uptime": (
                        datetime.now(timezone.utc)
                        - datetime.fromisoformat(str(tunnel_info["started_at"]))
                    ).seconds,
                }
            )
        )


class StatusHandler(tornado.web.RequestHandler):
    """Status endpoint with tunnel URL"""

    def get(self):
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(tunnel_info))

    def post(self):
        """Allow updating tunnel info"""
        try:
            data = json.loads(self.request.body)
            if "tunnel_url" in data:
                tunnel_info["tunnel_url"] = data["tunnel_url"]
                tunnel_info["status"] = "ready"
                logger.info(f"Tunnel URL updated: {data['tunnel_url']}")
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps({"success": True}))
        except Exception as e:
            logger.error(f"Error updating status: {e}")
            self.set_status(400)
            self.write(json.dumps({"error": str(e)}))


# Tornado application
application = tornado.web.Application(
    [
        (r"/websocket", TermSocket, {"term_manager": term_manager}),
        (r"/health", HealthHandler),
        (r"/status", StatusHandler),
        (
            r"/()",
            tornado.web.StaticFileHandler,
            {"path": "/app", "default_filename": "index.html"},
        ),
    ]
)

if __name__ == "__main__":
    logger.info("Starting Terminado server on port 8888")
    application.listen(8888)
    tornado.ioloop.IOLoop.current().start()
