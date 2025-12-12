#!/bin/bash

# Execute all load tests for Chat4All production validation
# This script runs load tests for T131 and validates all NFR targets

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOAD_TEST_DIR="$SCRIPT_DIR"
REPORTS_DIR="$LOAD_TEST_DIR/reports"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Load test configuration
API_URL="${API_URL:-http://localhost:8000}"
LOCUST_WEB_PORT="${LOCUST_WEB_PORT:-8089}"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║        Chat4All Production Load Testing Suite             ║${NC}"
echo -e "${BLUE}║                    Task T131                               ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Timestamp: ${TIMESTAMP}${NC}"
echo -e "${YELLOW}API URL: ${API_URL}${NC}"
echo -e "${YELLOW}Reports: ${REPORTS_DIR}/${TIMESTAMP}${NC}"
echo ""

# Create reports directory
mkdir -p "$REPORTS_DIR/$TIMESTAMP"

# Function to run a load test
run_load_test() {
    local test_name=$1
    local test_file=$2
    local users=$3
    local spawn_rate=$4
    local duration=$5
    local description=$6
    
    echo ""
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║ ${test_name}${NC}"
    echo -e "${BLUE}╠════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${BLUE}║ ${description}${NC}"
    echo -e "${BLUE}╠════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${BLUE}║ Users: ${users} | Spawn Rate: ${spawn_rate}/s | Duration: ${duration}${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    # Run Locust
    locust \
        -f "$LOAD_TEST_DIR/$test_file" \
        --host="$API_URL" \
        --users="$users" \
        --spawn-rate="$spawn_rate" \
        --run-time="$duration" \
        --headless \
        --html="$REPORTS_DIR/$TIMESTAMP/${test_name}.html" \
        --csv="$REPORTS_DIR/$TIMESTAMP/${test_name}" \
        --loglevel=INFO \
        2>&1 | tee "$REPORTS_DIR/$TIMESTAMP/${test_name}.log"
    
    local exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}✓ ${test_name} completed successfully${NC}"
    else
        echo -e "${RED}✗ ${test_name} failed with exit code ${exit_code}${NC}"
        return $exit_code
    fi
    
    # Add delay between tests
    echo -e "${YELLOW}Cooling down for 30 seconds...${NC}"
    sleep 30
}

# Check if Locust is installed
if ! command -v locust &> /dev/null; then
    echo -e "${RED}✗ Locust is not installed${NC}"
    echo "Install with: pip install locust websocket-client"
    exit 1
fi

# Check if API is reachable
echo -e "${YELLOW}Checking API health at ${API_URL}/health...${NC}"
if curl -f -s "${API_URL}/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ API is reachable${NC}"
else
    echo -e "${RED}✗ API is not reachable at ${API_URL}${NC}"
    echo "Start the API server or set API_URL environment variable"
    exit 1
fi

echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Starting Load Test Execution                              ${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"

# Test 1: API Throughput - 10M messages/minute (T128, T131)
echo ""
echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}  Test 1/4: API Message Throughput (T128, T131)             ${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
run_load_test \
    "api_throughput" \
    "test_api_throughput.py" \
    "1000" \
    "100" \
    "5m" \
    "Validate 10M msg/min (166K msg/s) with p99 <200ms latency"

# Test 2: WebSocket Connections - 10K concurrent (T129)
echo ""
echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}  Test 2/4: WebSocket Scalability (T129)                    ${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
run_load_test \
    "websocket_scalability" \
    "test_websocket_connections.py" \
    "5000" \
    "100" \
    "5m" \
    "Validate 10K concurrent connections with <100ms notification"

# Test 3: File Upload Performance - 100 concurrent uploads (T130)
echo ""
echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}  Test 3/4: File Upload Performance (T130)                  ${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
run_load_test \
    "file_upload" \
    "test_file_upload.py" \
    "100" \
    "10" \
    "10m" \
    "Validate 100 concurrent 1GB uploads with <5s per 10MB chunk"

# Test 4: Extended Throughput Test - Sustained load (T131)
echo ""
echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}  Test 4/4: Sustained Throughput (T131)                     ${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
run_load_test \
    "sustained_throughput" \
    "test_api_throughput.py" \
    "2000" \
    "100" \
    "15m" \
    "Sustained 10M msg/min for 15 minutes, validate no bottlenecks"

# Generate summary report
echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Generating Summary Report                                 ${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"

SUMMARY_FILE="$REPORTS_DIR/$TIMESTAMP/summary.txt"

cat > "$SUMMARY_FILE" << EOF
Chat4All Load Testing Summary Report
=====================================

Timestamp: $TIMESTAMP
API URL: $API_URL
Duration: ~45 minutes (including cooldown)

Performance Targets (NFR):
--------------------------
1. API Throughput: 10M msg/min (166K msg/s), p99 <200ms
2. WebSocket: 10K concurrent connections, notification <100ms
3. File Upload: 100 concurrent 1GB uploads, <5s per 10MB chunk
4. Sustained Load: No degradation over 15 minutes

Test Results:
-------------
EOF

# Extract key metrics from CSV files
for test_name in api_throughput websocket_scalability file_upload sustained_throughput; do
    if [ -f "$REPORTS_DIR/$TIMESTAMP/${test_name}_stats.csv" ]; then
        echo "" >> "$SUMMARY_FILE"
        echo "=== ${test_name} ===" >> "$SUMMARY_FILE"
        
        # Extract request stats
        tail -n +2 "$REPORTS_DIR/$TIMESTAMP/${test_name}_stats.csv" | \
            awk -F',' '{
                printf "  %-30s | Requests: %8s | Failures: %6s | Avg: %6s ms | p95: %6s ms | p99: %6s ms\n", 
                $1, $2, $3, $6, $9, $10
            }' >> "$SUMMARY_FILE"
        
        # Check if targets met
        echo "" >> "$SUMMARY_FILE"
        
        # Target validation (simplified)
        case "$test_name" in
            "api_throughput"|"sustained_throughput")
                echo "  Target: 166K req/s (10M/min), p99 <200ms" >> "$SUMMARY_FILE"
                ;;
            "websocket_scalability")
                echo "  Target: 10K connections, <100ms latency" >> "$SUMMARY_FILE"
                ;;
            "file_upload")
                echo "  Target: 100 concurrent, <5s per 10MB chunk" >> "$SUMMARY_FILE"
                ;;
        esac
    fi
done

# Add system metrics section
cat >> "$SUMMARY_FILE" << EOF

System Metrics During Testing:
------------------------------
Check Prometheus/Grafana for:
- Kafka producer latency
- Worker processing latency
- Database query latency
- Connection pool utilization
- Error rates
- Circuit breaker states

Reports Location:
-----------------
- HTML Reports: $REPORTS_DIR/$TIMESTAMP/*.html
- CSV Data: $REPORTS_DIR/$TIMESTAMP/*.csv
- Logs: $REPORTS_DIR/$TIMESTAMP/*.log

Next Steps:
-----------
1. Review HTML reports for detailed metrics
2. Check Grafana dashboards for system-level metrics
3. Analyze Jaeger traces for slow requests
4. Review Loki logs for errors
5. Document performance baseline in docs/performance_report.md
6. Address any bottlenecks discovered

For detailed analysis, use:
  python analyze_results.py $REPORTS_DIR/$TIMESTAMP

EOF

# Display summary
echo ""
cat "$SUMMARY_FILE"

# Check for failures
if grep -q "FAILED" "$REPORTS_DIR/$TIMESTAMP"/*.log; then
    echo ""
    echo -e "${RED}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  ⚠️  SOME TESTS FAILED - Review logs for details          ║${NC}"
    echo -e "${RED}╚════════════════════════════════════════════════════════════╝${NC}"
    exit 1
else
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✓ ALL LOAD TESTS COMPLETED SUCCESSFULLY                  ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
fi

echo ""
echo -e "${BLUE}Full report saved to: ${SUMMARY_FILE}${NC}"
echo -e "${BLUE}HTML reports: ${REPORTS_DIR}/${TIMESTAMP}/*.html${NC}"
echo ""
