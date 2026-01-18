#!/bin/bash
# Run multiple benchmark iterations

ITERATIONS=10
RESULTS_FILE="benchmark_timings.txt"

echo "Running $ITERATIONS benchmark iterations..."
echo "Results will be saved to $RESULTS_FILE"
echo ""

# Clear previous results
> $RESULTS_FILE

for i in $(seq 1 $ITERATIONS); do
    echo "========================================"
    echo "Iteration $i of $ITERATIONS"
    echo "========================================"

    OUTPUT=$(/home/jupyter/public-terminals/simple_benchmark.sh 2>&1)

    # Extract timings from output
    API_TIME=$(echo "$OUTPUT" | grep "API Create Time:" | awk '{print $4}' | sed 's/s//')
    CONTAINER_TIME=$(echo "$OUTPUT" | grep "Container Ready:" | awk '{print $3}' | sed 's/s//')
    TOTAL_TIME=$(echo "$OUTPUT" | grep "Total Startup Time:" | awk '{print $4}' | sed 's/s//')
    TUNNEL_TIME=$(echo "$OUTPUT" | grep "Tunnel Acquisition:" | awk '{print $3}' | sed 's/s//')

    # Save to results file
    echo "$TOTAL_TIME,$API_TIME,$CONTAINER_TIME,$TUNNEL_TIME" >> $RESULTS_FILE

    echo "Total startup time: ${TOTAL_TIME}s"
    echo ""

    # Wait a bit between iterations
    if [ $i -lt $ITERATIONS ]; then
        sleep 2
    fi
done

echo ""
echo "========================================"
echo "AGGREGATE RESULTS"
echo "========================================"

# Calculate statistics
echo ""
echo "Total Startup Times (seconds):"
awk -F',' '{print $1}' $RESULTS_FILE | sort -n | awk '
BEGIN {
    count = 0
    sum = 0
}
{
    values[count] = $1
    sum += $1
    count++
}
END {
    # Mean
    mean = sum / count

    # Min/Max
    min = values[0]
    max = values[count-1]

    # Median
    if (count % 2 == 0) {
        median = (values[count/2-1] + values[count/2]) / 2
    } else {
        median = values[int(count/2)]
    }

    printf "  Count:  %d\n", count
    printf "  Min:    %.3fs\n", min
    printf "  Max:    %.3fs\n", max
    printf "  Mean:   %.3fs\n", mean
    printf "  Median: %.3fs\n", median
}
'

echo ""
echo "Breakdown by Component (Mean):"
awk -F',' '
BEGIN {
    api_sum = 0
    container_sum = 0
    tunnel_sum = 0
    count = 0
}
{
    api_sum += $2
    container_sum += $3
    tunnel_sum += $4
    count++
}
END {
    printf "  API Create:        %.3fs\n", api_sum / count
    printf "  Container Ready:   %.3fs\n", container_sum / count
    printf "  Tunnel Acquisition:%.3fs\n", tunnel_sum / count
}
' $RESULTS_FILE

echo ""
echo "Raw data saved to: $RESULTS_FILE"
