#!/bin/bash
set -e

# Redirect all stdout/stderr to a log file AND keep it on console
# exec > >(tee -a /var/log/container.log) 2>&1

report_error() {
    local error_message="$1"
    echo "ERROR: $error_message" >&2

    if [ -n "$API_CALLBACK_URL" ] && [ -n "$TERMINAL_ID" ]; then
        curl -X POST "${API_CALLBACK_URL}/status" \
            -H "Content-Type: application/json" \
            -d "{\"terminal_id\": \"${TERMINAL_ID}\", \"status\": \"failed\", \"error_message\": \"${error_message}\"}" \
            || echo "Failed to report error to API" >&2
    fi
    exit 1
}

print_startup_info() {
    echo "===== Terminal Container Starting =====" >&2
    echo "Terminal ID: ${TERMINAL_ID}" >&2
    echo "API Callback URL: ${API_CALLBACK_URL}" >&2
    echo "Localtunnel Host: ${LOCALTUNNEL_HOST}" >&2
}

start_terminado() {
    echo "Starting Terminado server..." >&2
    # Use nohup to ensure it stays running and redirect stdout/stderr
    nohup python /app/terminado_server.py > /tmp/terminado.log 2>&1 &
    echo $!
}

wait_for_terminado() {
    echo "Waiting for Terminado to start..." >&2
    for i in {1..30}; do
        if curl -s http://localhost:8888/health > /dev/null; then
            echo "Terminado is ready!" >&2
            return 0
        fi
        if [ $i -eq 30 ]; then
            echo "Terminado log output:" >&2
            cat /tmp/terminado.log >&2
            report_error "Terminado failed to start within 30 seconds"
        fi
        sleep 1
    done
}

start_localtunnel() {
    echo "Starting localtunnel..." >&2
    local lt_cmd="lt --port 8888"
    if [ -n "$LOCALTUNNEL_HOST" ] && [ "$LOCALTUNNEL_HOST" != "https://localtunnel.me" ]; then
        lt_cmd="$lt_cmd --host $LOCALTUNNEL_HOST"
    fi
    
    # Use nohup to ensure it stays running and redirect all output
    nohup $lt_cmd > /tmp/tunnel_output.txt 2>&1 &
    echo $!
}

get_tunnel_url() {
    echo "Waiting for tunnel URL..." >&2
    local tunnel_url=""
    for i in {1..60}; do
        if [ -f /tmp/tunnel_output.txt ]; then
            # Show current output for debugging
            echo "Current tunnel output (attempt $i):" >&2
            cat /tmp/tunnel_output.txt >&2
            
            # Try to match different localtunnel output formats
            tunnel_url=$(grep -oP 'https://[a-zA-Z0-9-]+\.loca\.lt' /tmp/tunnel_output.txt | head -1)
            if [ -z "$tunnel_url" ]; then
                tunnel_url=$(grep -oP 'your url is: \Khttps://.*' /tmp/tunnel_output.txt | head -1)
            fi

            if [ -n "$tunnel_url" ]; then
                echo "Tunnel URL obtained: $tunnel_url" >&2
                echo "$tunnel_url"
                return 0
            fi
        fi

        if [ $i -eq 60 ]; then
            echo "FINAL tunnel output content:" >&2
            cat /tmp/tunnel_output.txt >&2
            report_error "Failed to obtain tunnel URL within 60 seconds"
        fi
        sleep 1
    done
}

update_status_endpoints() {
    local tunnel_url="$1"
    
    if [ -z "$tunnel_url" ]; then
        echo "Error: update_status_endpoints called with empty tunnel_url" >&2
        return 1
    fi

    echo "Updating container status with tunnel URL: $tunnel_url" >&2
    # Update local terminado server status
    local status_resp
    status_resp=$(curl -s -X POST "http://localhost:8888/status" \
        -H "Content-Type: application/json" \
        -d "{\"tunnel_url\": \"${tunnel_url}\"}")
    echo "Terminado status update response: $status_resp" >&2

    if [ -n "$API_CALLBACK_URL" ] && [ -n "$TERMINAL_ID" ]; then
        echo "Reporting tunnel URL to API: ${API_CALLBACK_URL}/tunnel" >&2
        local api_resp
        api_resp=$(curl -s -X POST "${API_CALLBACK_URL}/tunnel" \
            -H "Content-Type: application/json" \
            -d "{\"terminal_id\": \"${TERMINAL_ID}\", \"tunnel_url\": \"${tunnel_url}\"}")
        echo "API tunnel report response: $api_resp" >&2
    fi
}

print_ready_info() {
    local tunnel_url="$1"
    echo "===== Terminal Container Ready =====" >&2
    echo "Tunnel URL: $tunnel_url" >&2
    echo "Terminal ID: $TERMINAL_ID" >&2
}

health_check_loop() {
    local terminado_pid="$1"
    local lt_pid="$2"

    echo "Starting health check loop (PIDs: Terminado=$terminado_pid, LT=$lt_pid)" >&2

    while true; do
        sleep 60
        if ! kill -0 $terminado_pid 2>/dev/null; then
            report_error "Terminado process died unexpectedly"
        fi

        if ! kill -0 $lt_pid 2>/dev/null; then
            echo "Warning: Localtunnel process died, restarting..." >&2
            # Re-run start_localtunnel and update pid
            start_localtunnel > /tmp/lt_pid_restart.txt
            lt_pid=$(tail -n 1 /tmp/lt_pid_restart.txt)
        fi
    done
}

main() {
    print_startup_info
    
    # Use temporary file to get PID to avoid $(...) hanging issues
    start_terminado > /tmp/terminado_pid.txt
    local terminado_pid=$(tail -n 1 /tmp/terminado_pid.txt)
    
    wait_for_terminado

    start_localtunnel > /tmp/lt_pid.txt
    local lt_pid=$(tail -n 1 /tmp/lt_pid.txt)
    
    # Separate declaration and assignment to ensure set -e works correctly
    local tunnel_url_full
    tunnel_url_full=$(get_tunnel_url)
    
    # Get only the last line (the URL) in case there's any stray output
    local tunnel_url
    tunnel_url=$(echo "$tunnel_url_full" | tail -n 1)
    
    update_status_endpoints "$tunnel_url"
    print_ready_info "$tunnel_url"
    health_check_loop "$terminado_pid" "$lt_pid"
}

main
