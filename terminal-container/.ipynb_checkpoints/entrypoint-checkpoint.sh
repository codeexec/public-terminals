#!/bin/bash
set -e

echo "===== Terminal Container Starting ====="
echo "Terminal ID: ${TERMINAL_ID}"
echo "API Callback URL: ${API_CALLBACK_URL}"
echo "Localtunnel Host: ${LOCALTUNNEL_HOST}"

# Function to report errors back to API
report_error() {
    local error_message="$1"
    echo "ERROR: $error_message"

    if [ -n "$API_CALLBACK_URL" ] && [ -n "$TERMINAL_ID" ]; then
        curl -X POST "${API_CALLBACK_URL}/status" \
            -H "Content-Type: application/json" \
            -d "{\"terminal_id\": \"${TERMINAL_ID}\", \"status\": \"failed\", \"error_message\": \"${error_message}\"}" \
            || echo "Failed to report error to API"
    fi
    exit 1
}

# Create Terminado server script
cat > /tmp/terminado_server.py << 'EOF'
import tornado.ioloop
import tornado.web
from terminado import TermSocket, UniqueTermManager
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Terminal manager
term_manager = UniqueTermManager(shell_command=['bash'])

# Tornado application
application = tornado.web.Application([
    (r"/websocket", TermSocket, {'term_manager': term_manager}),
    (r"/()", tornado.web.StaticFileHandler, {
        'path': '/tmp',
        'default_filename': 'index.html'
    }),
])

if __name__ == "__main__":
    logger.info("Starting Terminado server on port 8888")
    application.listen(8888)
    tornado.ioloop.IOLoop.current().start()
EOF

# Create simple HTML interface for the terminal
cat > /tmp/index.html << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>Terminal</title>
    <style>
        body {
            margin: 0;
            padding: 0;
            background: #1e1e1e;
            color: #d4d4d4;
            font-family: 'Courier New', monospace;
        }
        #terminal {
            width: 100vw;
            height: 100vh;
            padding: 10px;
            box-sizing: border-box;
        }
        .header {
            background: #2d2d30;
            padding: 10px;
            border-bottom: 1px solid #3e3e42;
            font-size: 14px;
        }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.min.js"></script>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.css" />
</head>
<body>
    <div class="header">Terminal Session - Connected</div>
    <div id="terminal"></div>
    <script>
        const term = new Terminal({
            cursorBlink: true,
            fontSize: 14,
            theme: {
                background: '#1e1e1e',
                foreground: '#d4d4d4'
            }
        });
        term.open(document.getElementById('terminal'));

        const ws = new WebSocket('ws://' + window.location.host + '/websocket');

        ws.onopen = function() {
            console.log('WebSocket connected');
        };

        ws.onmessage = function(event) {
            term.write(event.data);
        };

        term.onData(function(data) {
            ws.send(JSON.stringify(['stdin', data]));
        });

        ws.onerror = function(error) {
            console.error('WebSocket error:', error);
        };
    </script>
</body>
</html>
EOF

echo "Starting Terminado server..."
python /tmp/terminado_server.py &
TERMINADO_PID=$!

# Wait for Terminado to be ready
echo "Waiting for Terminado to start..."
for i in {1..30}; do
    if curl -s http://localhost:8888 > /dev/null; then
        echo "Terminado is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        report_error "Terminado failed to start within 30 seconds"
    fi
    sleep 1
done

# Start localtunnel
echo "Starting localtunnel..."
if [ -n "$LOCALTUNNEL_HOST" ] && [ "$LOCALTUNNEL_HOST" != "https://localtunnel.me" ]; then
    # Use custom localtunnel server
    lt --port 8888 --host "$LOCALTUNNEL_HOST" > /tmp/tunnel_output.txt 2>&1 &
else
    # Use public localtunnel
    lt --port 8888 > /tmp/tunnel_output.txt 2>&1 &
fi
LT_PID=$!

# Wait for tunnel URL
echo "Waiting for tunnel URL..."
TUNNEL_URL=""
for i in {1..60}; do
    if [ -f /tmp/tunnel_output.txt ]; then
        TUNNEL_URL=$(grep -oP 'https://[a-zA-Z0-9-]+\.loca\.lt' /tmp/tunnel_output.txt | head -1)
        if [ -z "$TUNNEL_URL" ]; then
            TUNNEL_URL=$(grep -oP 'your url is: \Khttps://.*' /tmp/tunnel_output.txt | head -1)
        fi

        if [ -n "$TUNNEL_URL" ]; then
            echo "Tunnel URL obtained: $TUNNEL_URL"
            break
        fi
    fi

    if [ $i -eq 60 ]; then
        cat /tmp/tunnel_output.txt
        report_error "Failed to obtain tunnel URL within 60 seconds"
    fi
    sleep 1
done

# Report tunnel URL to API
if [ -n "$API_CALLBACK_URL" ] && [ -n "$TERMINAL_ID" ]; then
    echo "Reporting tunnel URL to API..."
    curl -X POST "${API_CALLBACK_URL}/tunnel" \
        -H "Content-Type: application/json" \
        -d "{\"terminal_id\": \"${TERMINAL_ID}\", \"tunnel_url\": \"${TUNNEL_URL}\"}" \
        || echo "Warning: Failed to report tunnel URL to API"
fi

echo "===== Terminal Container Ready ====="
echo "Tunnel URL: $TUNNEL_URL"
echo "Terminal ID: $TERMINAL_ID"

# Health check loop (optional - keeps container running and reports health)
while true; do
    sleep 60

    # Check if Terminado is still running
    if ! kill -0 $TERMINADO_PID 2>/dev/null; then
        report_error "Terminado process died unexpectedly"
    fi

    # Check if localtunnel is still running
    if ! kill -0 $LT_PID 2>/dev/null; then
        echo "Warning: Localtunnel process died, restarting..."
        lt --port 8888 > /tmp/tunnel_output.txt 2>&1 &
        LT_PID=$!
    fi
done
