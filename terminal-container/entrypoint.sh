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
    if [[ -n "${API_CALLBACK_URL:-}" && -n "${TERMINAL_ID:-}" ]]; then
        curl -s -X POST "${API_CALLBACK_URL}/status" \
            -H "Content-Type: application/json" \
            -d "{\"terminal_id\": \"${TERMINAL_ID}\", \"status\": \"failed\", \"error_message\": \"${msg}\"}" || true
    fi
    exit 1
}

wait_for_ready() {
    local url="$1" label="$2" timeout="${3:-30}"
    log "Waiting for $label to be ready..."
    for ((i=1; i<=timeout; i++)); do
        if curl -s "$url" >/dev/null; then
            log "$label is ready!"
            return 0
        fi
        sleep 1
    done
    report_error "$label failed to start within $timeout seconds"
}

get_tunnel_url() {
    for ((i=1; i<=60; i++)); do
        if [[ -f "$TUNNEL_FILE" ]]; then
            # Extract URL using grep; supports standard and custom lt output
            local url
            url=$(grep -oP '(https?://[a-zA-Z0-9.-]+\.[a-z]+)' "$TUNNEL_FILE" | grep -v 'localtunnel.me' | head -1 || true)
            if [[ -n "$url" ]]; then
                echo "$url"
                return 0
            fi
        fi
        sleep 1
    done
    log "Final tunnel output:" && cat "$TUNNEL_FILE" >&2
    report_error "Failed to obtain tunnel URL within 60 seconds"
}

update_status() {
    local url="$1"
    log "Reporting tunnel URL: $url"
    
    # Update local server
    curl -s -X POST "http://localhost:$PORT/status" \
        -H "Content-Type: application/json" \
        -d "{\"tunnel_url\": \"$url\"}" >/dev/null || log "Warning: Local status update failed"

    # Update API
    if [[ -n "${API_CALLBACK_URL:-}" ]]; then
        curl -s -X POST "${API_CALLBACK_URL}/tunnel" \
            -H "Content-Type: application/json" \
            -d "{\"terminal_id\": \"$TERMINAL_ID\", \"tunnel_url\": \"$url\"}" >/dev/null || log "Warning: API callback failed"
    fi
}

main() {
    log "Starting Terminal Container (ID: ${TERMINAL_ID:-unknown})"

    # Start Terminado
    nohup python /app/terminado_server.py > /tmp/terminado.log 2>&1 &
    local term_pid=$!
    wait_for_ready "http://localhost:$PORT/health" "Terminado"

    # Start Stats Reporter
    if [[ -n "${API_CALLBACK_URL:-}" ]]; then
        log "Starting stats reporter..."
        nohup python /app/stats_reporter.py > /tmp/stats_reporter.log 2>&1 &
        local stats_pid=$!
        log "Stats reporter started (PID: $stats_pid)"
    fi

    # Start Idle Monitor
    if [[ -n "${API_CALLBACK_URL:-}" ]]; then
        local timeout_seconds="${TERMINAL_IDLE_TIMEOUT_SECONDS:-3600}"
        local timeout_minutes=$((timeout_seconds / 60))
        log "Starting idle monitor (timeout: ${timeout_minutes} minutes / ${timeout_seconds} seconds)..."
        nohup python /app/idle_monitor.py > /tmp/idle_monitor.log 2>&1 &
        local idle_pid=$!
        log "Idle monitor started (PID: $idle_pid)"
    fi

    # Start Localtunnel
    local lt_cmd="lt --port $PORT"
    [[ -n "${LOCALTUNNEL_HOST:-}" ]] && lt_cmd+=" --host $LOCALTUNNEL_HOST"
    nohup $lt_cmd > "$TUNNEL_FILE" 2>&1 &
    local lt_pid=$!

    # Get and report URL
    local tunnel_url
    tunnel_url=$(get_tunnel_url)
    update_status "$tunnel_url"

    log "Terminal ready at: $tunnel_url"

    # Health check loop
    while true; do
        sleep 60
        kill -0 "$term_pid" 2>/dev/null || report_error "Terminado died"
        if ! kill -0 "$lt_pid" 2>/dev/null; then
            log "Localtunnel died, restarting..."
            nohup $lt_cmd > "$TUNNEL_FILE" 2>&1 &
            lt_pid=$!
        fi
    done
}

main