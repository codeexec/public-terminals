#!/bin/bash
set -euo pipefail

# Constants
PORT=8888
LOG_FILE="/tmp/container.log"
TUNNEL_FILE="/tmp/tunnel_output.txt"

log() { echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')] $*" >&2; }

report_error() {
    local msg="$1"
    log "ERROR: $msg"
    if [[ -n "${API_CALLBACK_URL:-}" && -n "${TERMINAL_ID:-}" && -n "${CALLBACK_TOKEN:-}" ]]; then
        curl -s -X POST "${API_CALLBACK_URL}/status" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer ${CALLBACK_TOKEN}" \
            -d "{\"sandbox_id\": \"${TERMINAL_ID}\", \"status\": \"failed\", \"error_message\": \"${msg}\"}" || true
    fi
    exit 1
}

wait_for_ready() {
    local url="$1" label="$2" timeout="${3:-30}"
    log "Waiting for $label to be ready..."
    for ((i=1; i<=timeout*4; i++)); do
        if curl -s --max-time 1 "$url" >/dev/null 2>&1; then
            log "$label is ready!"
            return 0
        fi
        sleep 0.25
    done
    report_error "$label failed to start within $timeout seconds"
}

get_tunnel_url() {
    local max_wait="${1:-60}"
    for ((i=1; i<=max_wait*4; i++)); do
        if [[ -f "$TUNNEL_FILE" ]]; then
            local url
            url=$(grep -oP '(https?://[a-zA-Z0-9.-]+\.[a-z]+)' "$TUNNEL_FILE" 2>/dev/null | grep -v 'localtunnel.me' | head -1 || true)
            if [[ -n "$url" ]]; then
                echo "$url"
                return 0
            fi
        fi
        sleep 0.25
    done
    log "Final tunnel output:" && cat "$TUNNEL_FILE" >&2 2>/dev/null || true
    report_error "Failed to obtain tunnel URL within $max_wait seconds"
}

update_status() {
    local url="$1"
    log "Reporting tunnel URL: $url"

    curl -s --max-time 2 -X POST "http://localhost:$PORT/status" \
        -H "Content-Type: application/json" \
        -d "{\"tunnel_url\": \"$url\"}" >/dev/null 2>&1 || log "Warning: Local status update failed"

    if [[ -n "${API_CALLBACK_URL:-}" && -n "${CALLBACK_TOKEN:-}" ]]; then
        curl -s --max-time 5 -X POST "${API_CALLBACK_URL}/tunnel" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer ${CALLBACK_TOKEN}" \
            -d "{\"sandbox_id\": \"$TERMINAL_ID\", \"tunnel_url\": \"$url\"}" >/dev/null 2>&1 || log "Warning: API callback failed"
    fi
}

main() {
    log "Starting JupyterLite Sandbox (ID: ${TERMINAL_ID:-unknown})"

    rm -f "$TUNNEL_FILE"

    local lt_cmd="lt --port $PORT"
    [[ -n "${LOCALTUNNEL_HOST:-}" ]] && lt_cmd+=" --host $LOCALTUNNEL_HOST"

    log "Starting Localtunnel..."
    nohup $lt_cmd > "$TUNNEL_FILE" 2>&1 &
    local lt_pid=$!

    log "Starting JupyterLite server..."
    nohup python /app/jupyterlite_server.py > /tmp/jupyterlite.log 2>&1 &
    local server_pid=$!

    wait_for_ready "http://localhost:$PORT/health" "JupyterLite Server" 30

    if [[ -n "${API_CALLBACK_URL:-}" ]]; then
        nohup python /app/stats_reporter.py > /tmp/stats_reporter.log 2>&1 &
        nohup python /app/idle_monitor.py > /tmp/idle_monitor.log 2>&1 &
        log "Background services started"
    fi

    local tunnel_url
    tunnel_url=$(get_tunnel_url 60)
    update_status "$tunnel_url"

    log "JupyterLite ready at: $tunnel_url"

    while true; do
        sleep 60
        if ! kill -0 "$server_pid" 2>/dev/null; then
            report_error "JupyterLite server process died"
        fi
        if ! kill -0 "$lt_pid" 2>/dev/null; then
            log "Localtunnel died, restarting..."
            rm -f "$TUNNEL_FILE"
            nohup $lt_cmd > "$TUNNEL_FILE" 2>&1 &
            lt_pid=$!
            sleep 2
            local new_url
            new_url=$(get_tunnel_url 30) || true
            if [[ -n "$new_url" ]]; then
                update_status "$new_url"
                log "Tunnel reconnected at: $new_url"
            fi
        fi
    done
}

main
