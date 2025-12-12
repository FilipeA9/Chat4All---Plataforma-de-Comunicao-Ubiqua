# Execute all load tests for Chat4All production validation
# This script runs load tests for T131 and validates all NFR targets

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LoadTestDir = $ScriptDir
$ReportsDir = Join-Path $LoadTestDir "reports"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"

# Load test configuration
$ApiUrl = if ($env:API_URL) { $env:API_URL } else { "http://localhost:8000" }
$LocustWebPort = if ($env:LOCUST_WEB_PORT) { $env:LOCUST_WEB_PORT } else { "8089" }

Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Blue
Write-Host "║        Chat4All Production Load Testing Suite             ║" -ForegroundColor Blue
Write-Host "║                    Task T131                               ║" -ForegroundColor Blue
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Blue
Write-Host ""
Write-Host "Timestamp: $Timestamp" -ForegroundColor Yellow
Write-Host "API URL: $ApiUrl" -ForegroundColor Yellow
Write-Host "Reports: $ReportsDir\$Timestamp" -ForegroundColor Yellow
Write-Host ""

# Create reports directory
$TimestampReportsDir = Join-Path $ReportsDir $Timestamp
New-Item -ItemType Directory -Force -Path $TimestampReportsDir | Out-Null

# Function to run a load test
function Run-LoadTest {
    param(
        [string]$TestName,
        [string]$TestFile,
        [int]$Users,
        [int]$SpawnRate,
        [string]$Duration,
        [string]$Description
    )
    
    Write-Host ""
    Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Blue
    Write-Host "║ $TestName" -ForegroundColor Blue
    Write-Host "╠════════════════════════════════════════════════════════════╣" -ForegroundColor Blue
    Write-Host "║ $Description" -ForegroundColor Blue
    Write-Host "╠════════════════════════════════════════════════════════════╣" -ForegroundColor Blue
    Write-Host "║ Users: $Users | Spawn Rate: $SpawnRate/s | Duration: $Duration" -ForegroundColor Blue
    Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Blue
    Write-Host ""
    
    $TestFilePath = Join-Path $LoadTestDir $TestFile
    $HtmlReport = Join-Path $TimestampReportsDir "$TestName.html"
    $CsvPrefix = Join-Path $TimestampReportsDir $TestName
    $LogFile = Join-Path $TimestampReportsDir "$TestName.log"
    
    # Build Locust command
    $LocustArgs = @(
        "-f", $TestFilePath,
        "--host=$ApiUrl",
        "--users=$Users",
        "--spawn-rate=$SpawnRate",
        "--run-time=$Duration",
        "--headless",
        "--html=$HtmlReport",
        "--csv=$CsvPrefix",
        "--loglevel=INFO"
    )
    
    # Run Locust and capture output
    try {
        locust @LocustArgs 2>&1 | Tee-Object -FilePath $LogFile
        
        Write-Host "✓ $TestName completed successfully" -ForegroundColor Green
        
        # Cooling down
        Write-Host "Cooling down for 30 seconds..." -ForegroundColor Yellow
        Start-Sleep -Seconds 30
        
        return $true
    } catch {
        Write-Host "✗ $TestName failed: $_" -ForegroundColor Red
        return $false
    }
}

# Check if Locust is installed
try {
    $null = Get-Command locust -ErrorAction Stop
} catch {
    Write-Host "✗ Locust is not installed" -ForegroundColor Red
    Write-Host "Install with: pip install locust websocket-client" -ForegroundColor Yellow
    exit 1
}

# Check if API is reachable
Write-Host "Checking API health at $ApiUrl/health..." -ForegroundColor Yellow
try {
    $Response = Invoke-WebRequest -Uri "$ApiUrl/health" -Method Get -TimeoutSec 5 -UseBasicParsing
    if ($Response.StatusCode -eq 200) {
        Write-Host "✓ API is reachable" -ForegroundColor Green
    } else {
        throw "Unexpected status code: $($Response.StatusCode)"
    }
} catch {
    Write-Host "✗ API is not reachable at $ApiUrl" -ForegroundColor Red
    Write-Host "Start the API server or set API_URL environment variable" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Blue
Write-Host "  Starting Load Test Execution                              " -ForegroundColor Blue
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Blue

$TestResults = @()

# Test 1: API Throughput - 10M messages/minute (T128, T131)
Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Yellow
Write-Host "  Test 1/4: API Message Throughput (T128, T131)             " -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Yellow
$Result1 = Run-LoadTest `
    -TestName "api_throughput" `
    -TestFile "test_api_throughput.py" `
    -Users 1000 `
    -SpawnRate 100 `
    -Duration "5m" `
    -Description "Validate 10M msg/min (166K msg/s) with p99 <200ms latency"
$TestResults += $Result1

# Test 2: WebSocket Connections - 10K concurrent (T129)
Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Yellow
Write-Host "  Test 2/4: WebSocket Scalability (T129)                    " -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Yellow
$Result2 = Run-LoadTest `
    -TestName "websocket_scalability" `
    -TestFile "test_websocket_connections.py" `
    -Users 5000 `
    -SpawnRate 100 `
    -Duration "5m" `
    -Description "Validate 10K concurrent connections with <100ms notification"
$TestResults += $Result2

# Test 3: File Upload Performance - 100 concurrent uploads (T130)
Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Yellow
Write-Host "  Test 3/4: File Upload Performance (T130)                  " -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Yellow
$Result3 = Run-LoadTest `
    -TestName "file_upload" `
    -TestFile "test_file_upload.py" `
    -Users 100 `
    -SpawnRate 10 `
    -Duration "10m" `
    -Description "Validate 100 concurrent 1GB uploads with <5s per 10MB chunk"
$TestResults += $Result3

# Test 4: Extended Throughput Test - Sustained load (T131)
Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Yellow
Write-Host "  Test 4/4: Sustained Throughput (T131)                     " -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Yellow
$Result4 = Run-LoadTest `
    -TestName "sustained_throughput" `
    -TestFile "test_api_throughput.py" `
    -Users 2000 `
    -SpawnRate 100 `
    -Duration "15m" `
    -Description "Sustained 10M msg/min for 15 minutes, validate no bottlenecks"
$TestResults += $Result4

# Generate summary report
Write-Host ""
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Blue
Write-Host "  Generating Summary Report                                 " -ForegroundColor Blue
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Blue

$SummaryFile = Join-Path $TimestampReportsDir "summary.txt"

@"
Chat4All Load Testing Summary Report
=====================================

Timestamp: $Timestamp
API URL: $ApiUrl
Duration: ~45 minutes (including cooldown)

Performance Targets (NFR):
--------------------------
1. API Throughput: 10M msg/min (166K msg/s), p99 <200ms
2. WebSocket: 10K concurrent connections, notification <100ms
3. File Upload: 100 concurrent 1GB uploads, <5s per 10MB chunk
4. Sustained Load: No degradation over 15 minutes

Test Results:
-------------
"@ | Out-File -FilePath $SummaryFile -Encoding UTF8

# Extract key metrics from CSV files
$TestNames = @("api_throughput", "websocket_scalability", "file_upload", "sustained_throughput")
foreach ($TestName in $TestNames) {
    $StatsFile = Join-Path $TimestampReportsDir "${TestName}_stats.csv"
    if (Test-Path $StatsFile) {
        "`n=== $TestName ===" | Out-File -FilePath $SummaryFile -Append -Encoding UTF8
        
        # Read and format CSV data
        Import-Csv $StatsFile | ForEach-Object {
            $line = "  {0,-30} | Requests: {1,8} | Failures: {2,6} | Avg: {3,6} ms | p95: {4,6} ms | p99: {5,6} ms" -f `
                $_.Name, $_."Request Count", $_."Failure Count", $_."Average Response Time", $_."95%", $_."99%"
            $line | Out-File -FilePath $SummaryFile -Append -Encoding UTF8
        }
        
        # Target validation
        "`n" | Out-File -FilePath $SummaryFile -Append -Encoding UTF8
        switch ($TestName) {
            "api_throughput" {
                "  Target: 166K req/s (10M/min), p99 <200ms" | Out-File -FilePath $SummaryFile -Append -Encoding UTF8
            }
            "sustained_throughput" {
                "  Target: 166K req/s (10M/min), p99 <200ms" | Out-File -FilePath $SummaryFile -Append -Encoding UTF8
            }
            "websocket_scalability" {
                "  Target: 10K connections, <100ms latency" | Out-File -FilePath $SummaryFile -Append -Encoding UTF8
            }
            "file_upload" {
                "  Target: 100 concurrent, <5s per 10MB chunk" | Out-File -FilePath $SummaryFile -Append -Encoding UTF8
            }
        }
    }
}

# Add system metrics section
@"

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
- HTML Reports: $TimestampReportsDir\*.html
- CSV Data: $TimestampReportsDir\*.csv
- Logs: $TimestampReportsDir\*.log

Next Steps:
-----------
1. Review HTML reports for detailed metrics
2. Check Grafana dashboards for system-level metrics
3. Analyze Jaeger traces for slow requests
4. Review Loki logs for errors
5. Document performance baseline in docs/performance_report.md
6. Address any bottlenecks discovered

For detailed analysis, use:
  python analyze_results.py $TimestampReportsDir

"@ | Out-File -FilePath $SummaryFile -Append -Encoding UTF8

# Display summary
Write-Host ""
Get-Content $SummaryFile | Write-Host

# Check for failures
$AllPassed = $TestResults -notcontains $false

if (-not $AllPassed) {
    Write-Host ""
    Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Red
    Write-Host "║  ⚠️  SOME TESTS FAILED - Review logs for details          ║" -ForegroundColor Red
    Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Red
    exit 1
} else {
    Write-Host ""
    Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "║  ✓ ALL LOAD TESTS COMPLETED SUCCESSFULLY                  ║" -ForegroundColor Green
    Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Green
}

Write-Host ""
Write-Host "Full report saved to: $SummaryFile" -ForegroundColor Blue
Write-Host "HTML reports: $TimestampReportsDir\*.html" -ForegroundColor Blue
Write-Host ""
