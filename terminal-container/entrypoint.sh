#!/bin/bash
set -e

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

print_startup_info() {
    echo "===== Terminal Container Starting ====="
    echo "Terminal ID: ${TERMINAL_ID}"
    echo "API Callback URL: ${API_CALLBACK_URL}"
    echo "Localtunnel Host: ${LOCALTUNNEL_HOST}"
}

start_terminado() {
    echo "Starting Terminado server..."
    python /app/terminado_server.py &
    echo $!
}

wait_for_terminado() {
    echo "Waiting for Terminado to start..."
    for i in {1..30}; do
        if curl -s http://localhost:8888 > /dev/null; then
            echo "Terminado is ready!"
            return 0
        fi
        if [ $i -eq 30 ]; then
            report_error "Terminado failed to start within 30 seconds"
        fi
        sleep 1
    done
}

start_localtunnel() {
    echo "Starting localtunnel..."
    if [ -n "$LOCALTUNNEL_HOST" ] && [ "$LOCALTUNNEL_HOST" != "https://localtunnel.me" ]; then
        lt --port 8888 --host "$LOCALTUNNEL_HOST" > /tmp/tunnel_output.txt 2>&1 &
    else
        lt --port 8888 > /tmp/tunnel_output.txt 2>&1 &
    fi
    echo $!
}

get_tunnel_url() {
    echo "Waiting for tunnel URL..."
    local tunnel_url=""
    for i in {1..60}; do
        if [ -f /tmp/tunnel_output.txt ]; then
            tunnel_url=$(grep -oP 'https://[a-zA-Z0-9-]+\.loca\.lt' /tmp/tunnel_output.txt | head -1)
            if [ -z "$tunnel_url" ]; then
                tunnel_url=$(grep -oP 'your url is: \Khttps://.*' /tmp/tunnel_output.txt | head -1)
            fi

            if [ -n "$tunnel_url" ]; then
                echo "Tunnel URL obtained: $tunnel_url"
                echo "$tunnel_url"
                return 0
            fi
        fi

        if [ $i -eq 60 ]; then
            cat /tmp/tunnel_output.txt
            report_error "Failed to obtain tunnel URL within 60 seconds"
        fi
        sleep 1
    done
}

update_status_endpoints() {
    local tunnel_url="$1"

    echo "Updating container status with tunnel URL..."
    curl -X POST "http://localhost:8888/status" \
        -H "Content-Type: application/json" \
        -d "{\"tunnel_url\": \"${tunnel_url}\"}" \
        || echo "Warning: Failed to update container status"

    if [ -n "$API_CALLBACK_URL" ] && [ -n "$TERMINAL_ID" ]; then
        echo "Reporting tunnel URL to API..."
        curl -X POST "${API_CALLBACK_URL}/tunnel" \
            -H "Content-Type: application/json" \
            -d "{\"terminal_id\": \"${TERMINAL_ID}\", \"tunnel_url\": \"${tunnel_url}\"}" \
            || echo "Warning: Failed to report tunnel URL to API"
    fi
}

print_ready_info() {
    local tunnel_url="$1"
    echo "===== Terminal Container Ready ====="
    echo "Tunnel URL: $tunnel_url"
    echo "Terminal ID: $TERMINAL_ID"
    echo "Health endpoint: http://localhost:8888/health"
    echo "Status endpoint: http://localhost:8888/status"
}

health_check_loop() {
    local terminado_pid="$1"
    local lt_pid="$2"

    while true; do
        sleep 60
        if ! kill -0 $terminado_pid 2>/dev/null; then
            report_error "Terminado process died unexpectedly"
        fi

        if ! kill -0 $lt_pid 2>/dev/null; then
            echo "Warning: Localtunnel process died, restarting..."
            lt_pid=$(start_localtunnel)
        fi
    done
}

main() {
    print_startup_info
    local terminado_pid=$(start_terminado)
    wait_for_terminado

    local lt_pid=$(start_localtunnel)
    local tunnel_url=$(get_tunnel_url)
    update_status_endpoints "$tunnel_url"
    print_ready_info "$tunnel_url"
    health_check_loop "$terminado_pid" "$lt_pid"
}

main