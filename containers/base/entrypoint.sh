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

# Optimized: Faster health check with shorter intervals
wait_for_ready() {
    local url="$1" label="$2" timeout="${3:-30}"
    log "Waiting for $label to be ready..."
    for ((i=1; i<=timeout*4; i++)); do
        if curl -s --max-time 1 "$url" >/dev/null 2>&1; then
            log "$label is ready!"
            return 0
        fi
        sleep 0.25  # Check 4x per second for faster detection
    done
    report_error "$label failed to start within $timeout seconds"
}

# Optimized: Faster tunnel URL detection
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
        sleep 0.25  # Check 4x per second
    done
    log "Final tunnel output:" && cat "$TUNNEL_FILE" >&2 2>/dev/null || true
    report_error "Failed to obtain tunnel URL within $max_wait seconds"
}

update_status() {
    local url="$1"
    log "Reporting tunnel URL: $url"

    # Update local server (fire and forget with short timeout)
    curl -s --max-time 2 -X POST "http://localhost:$PORT/status" \
        -H "Content-Type: application/json" \
        -d "{\"tunnel_url\": \"$url\"}" >/dev/null 2>&1 || log "Warning: Local status update failed"

    # Update API
    if [[ -n "${API_CALLBACK_URL:-}" && -n "${CALLBACK_TOKEN:-}" ]]; then
        curl -s --max-time 5 -X POST "${API_CALLBACK_URL}/tunnel" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer ${CALLBACK_TOKEN}" \
            -d "{\"sandbox_id\": \"$TERMINAL_ID\", \"tunnel_url\": \"$url\"}" >/dev/null 2>&1 || log "Warning: API callback failed"
    fi
}

main() {
    log "Starting Sandbox Workspace (ID: ${TERMINAL_ID:-unknown})"

    # Clear any stale tunnel file
    rm -f "$TUNNEL_FILE"

    # Build localtunnel command
    local lt_cmd="lt --port $PORT"
    [[ -n "${LOCALTUNNEL_HOST:-}" ]] && lt_cmd+=" --host $LOCALTUNNEL_HOST"

    # OPTIMIZATION: Start both services simultaneously
    # Start Localtunnel FIRST (it takes longer to establish connection)
    log "Starting Localtunnel..."
    nohup $lt_cmd > "$TUNNEL_FILE" 2>&1 &
    local lt_pid=$!

    # Start Terminado immediately after
    log "Starting Terminado server..."
    nohup python /app/terminado_server.py > /tmp/terminado.log 2>&1 &
    local term_pid=$!

    # Wait for Terminado to be ready (usually faster than tunnel)
    wait_for_ready "http://localhost:$PORT/health" "Terminado" 30

    # Start background services in parallel (non-blocking)
    if [[ -n "${API_CALLBACK_URL:-}" ]]; then
        # Stats Reporter
        nohup python /app/stats_reporter.py > /tmp/stats_reporter.log 2>&1 &

        # Idle Monitor
        local timeout_seconds="${TERMINAL_IDLE_TIMEOUT_SECONDS:-3600}"
        nohup python /app/idle_monitor.py > /tmp/idle_monitor.log 2>&1 &
        log "Background services started"
    fi

    # Get tunnel URL (LT may already have it by now)
    local tunnel_url
    tunnel_url=$(get_tunnel_url 60)
    update_status "$tunnel_url"

    log "Sandbox ready at: $tunnel_url"

    # Health check loop with longer intervals (less CPU overhead)
    while true; do
        sleep 60

        # Check Terminado
        if ! kill -0 "$term_pid" 2>/dev/null; then
            report_error "Terminado process died"
        fi

        # Check and restart Localtunnel if needed
        if ! kill -0 "$lt_pid" 2>/dev/null; then
            log "Localtunnel died, restarting..."
            rm -f "$TUNNEL_FILE"
            nohup $lt_cmd > "$TUNNEL_FILE" 2>&1 &
            lt_pid=$!

            # Wait for new tunnel URL and update
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
