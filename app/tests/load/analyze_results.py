#!/usr/bin/env python3
"""
Analyze load test results and generate performance report.
This script parses Locust CSV outputs and validates against NFR targets.

Usage:
    python analyze_results.py <reports_directory>
    
Example:
    python analyze_results.py tests/load/reports/20251202_143000
"""

import sys
import os
import glob
import csv
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass
from datetime import datetime


@dataclass
class TestMetrics:
    """Load test metrics"""
    name: str
    request_count: int
    failure_count: int
    avg_response_time: float
    min_response_time: float
    max_response_time: float
    p50: float
    p95: float
    p99: float
    requests_per_second: float
    failure_rate: float


@dataclass
class PerformanceTarget:
    """NFR performance targets"""
    name: str
    description: str
    target_throughput: str
    target_latency: str
    target_p99: float  # milliseconds


# NFR Performance Targets
TARGETS = {
    "api_throughput": PerformanceTarget(
        name="API Message Throughput",
        description="Validate 10M msg/min (166K msg/s) with p99 <200ms",
        target_throughput="166,000 req/s",
        target_latency="<200ms p99",
        target_p99=200.0
    ),
    "sustained_throughput": PerformanceTarget(
        name="Sustained Message Throughput",
        description="Sustained 10M msg/min for 15 minutes",
        target_throughput="166,000 req/s",
        target_latency="<200ms p99",
        target_p99=200.0
    ),
    "websocket_scalability": PerformanceTarget(
        name="WebSocket Scalability",
        description="10K concurrent connections with <100ms notification",
        target_throughput="10,000 connections",
        target_latency="<100ms p99",
        target_p99=100.0
    ),
    "file_upload": PerformanceTarget(
        name="File Upload Performance",
        description="100 concurrent 1GB uploads with <5s per 10MB chunk",
        target_throughput="100 concurrent uploads",
        target_latency="<5000ms per chunk",
        target_p99=5000.0
    ),
}


def parse_stats_csv(csv_path: Path) -> List[TestMetrics]:
    """Parse Locust stats CSV file"""
    metrics = []
    
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Skip aggregated rows
            if row['Name'] == 'Aggregated':
                continue
            
            try:
                metrics.append(TestMetrics(
                    name=row['Name'],
                    request_count=int(row['Request Count']),
                    failure_count=int(row['Failure Count']),
                    avg_response_time=float(row['Average Response Time']),
                    min_response_time=float(row['Min Response Time']),
                    max_response_time=float(row['Max Response Time']),
                    p50=float(row['50%']),
                    p95=float(row['95%']),
                    p99=float(row['99%']),
                    requests_per_second=float(row['Requests/s']),
                    failure_rate=(int(row['Failure Count']) / int(row['Request Count']) * 100) 
                                 if int(row['Request Count']) > 0 else 0.0
                ))
            except (KeyError, ValueError) as e:
                print(f"Warning: Skipping row due to error: {e}")
                continue
    
    return metrics


def validate_target(test_name: str, metrics: List[TestMetrics]) -> Tuple[bool, str]:
    """Validate test results against NFR targets"""
    if test_name not in TARGETS:
        return True, "No target defined for this test"
    
    target = TARGETS[test_name]
    
    # Aggregate metrics
    total_requests = sum(m.request_count for m in metrics)
    total_failures = sum(m.failure_count for m in metrics)
    avg_p99 = sum(m.p99 * m.request_count for m in metrics) / total_requests if total_requests > 0 else 0
    failure_rate = (total_failures / total_requests * 100) if total_requests > 0 else 0
    
    # Check p99 latency
    passed = avg_p99 <= target.target_p99 and failure_rate < 1.0
    
    status = "PASSED ✓" if passed else "FAILED ✗"
    details = f"p99: {avg_p99:.2f}ms (target: <{target.target_p99}ms), " \
              f"failure_rate: {failure_rate:.2f}% (target: <1%)"
    
    return passed, f"{status} - {details}"


def generate_report(reports_dir: Path) -> str:
    """Generate comprehensive performance report"""
    report_lines = []
    
    # Header
    report_lines.append("=" * 80)
    report_lines.append("Chat4All Load Testing Performance Report")
    report_lines.append("=" * 80)
    report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"Reports Directory: {reports_dir}")
    report_lines.append("")
    
    # Find all stats CSV files
    stats_files = glob.glob(str(reports_dir / "*_stats.csv"))
    
    if not stats_files:
        report_lines.append("ERROR: No stats CSV files found in reports directory")
        return "\n".join(report_lines)
    
    all_passed = True
    
    # Analyze each test
    for stats_file in stats_files:
        test_name = Path(stats_file).stem.replace('_stats', '')
        report_lines.append("-" * 80)
        report_lines.append(f"Test: {test_name}")
        
        if test_name in TARGETS:
            target = TARGETS[test_name]
            report_lines.append(f"Description: {target.description}")
            report_lines.append(f"Target Throughput: {target.target_throughput}")
            report_lines.append(f"Target Latency: {target.target_latency}")
        
        report_lines.append("-" * 80)
        
        # Parse metrics
        try:
            metrics = parse_stats_csv(Path(stats_file))
        except Exception as e:
            report_lines.append(f"ERROR parsing {stats_file}: {e}")
            continue
        
        if not metrics:
            report_lines.append("No metrics found in file")
            continue
        
        # Display metrics table
        report_lines.append("")
        report_lines.append(f"{'Endpoint':<40} {'Requests':>10} {'Failures':>10} {'Fail %':>8} "
                          f"{'Avg (ms)':>10} {'p95 (ms)':>10} {'p99 (ms)':>10} {'RPS':>10}")
        report_lines.append("-" * 130)
        
        for m in metrics:
            report_lines.append(
                f"{m.name:<40} {m.request_count:>10} {m.failure_count:>10} {m.failure_rate:>7.2f}% "
                f"{m.avg_response_time:>10.2f} {m.p95:>10.2f} {m.p99:>10.2f} {m.requests_per_second:>10.2f}"
            )
        
        # Aggregate totals
        total_requests = sum(m.request_count for m in metrics)
        total_failures = sum(m.failure_count for m in metrics)
        total_rps = sum(m.requests_per_second for m in metrics)
        avg_p99 = sum(m.p99 * m.request_count for m in metrics) / total_requests if total_requests > 0 else 0
        
        report_lines.append("-" * 130)
        report_lines.append(f"{'TOTAL':<40} {total_requests:>10} {total_failures:>10} "
                          f"{(total_failures/total_requests*100 if total_requests > 0 else 0):>7.2f}% "
                          f"{'':>10} {'':>10} {avg_p99:>10.2f} {total_rps:>10.2f}")
        report_lines.append("")
        
        # Validation
        passed, validation_msg = validate_target(test_name, metrics)
        report_lines.append(f"Validation: {validation_msg}")
        report_lines.append("")
        
        if not passed:
            all_passed = False
    
    # Summary
    report_lines.append("=" * 80)
    report_lines.append("Summary")
    report_lines.append("=" * 80)
    
    if all_passed:
        report_lines.append("✓ ALL TESTS PASSED - System meets all NFR performance targets")
    else:
        report_lines.append("✗ SOME TESTS FAILED - Review results above for details")
    
    report_lines.append("")
    report_lines.append("Next Steps:")
    report_lines.append("1. Review Grafana dashboards for system-level metrics")
    report_lines.append("2. Analyze Jaeger traces for slow requests")
    report_lines.append("3. Check Prometheus for Kafka/DB latencies")
    report_lines.append("4. Review Loki logs for errors")
    report_lines.append("5. Document baseline in docs/performance_report.md")
    report_lines.append("6. Address any bottlenecks discovered")
    report_lines.append("")
    
    return "\n".join(report_lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_results.py <reports_directory>")
        print("Example: python analyze_results.py tests/load/reports/20251202_143000")
        sys.exit(1)
    
    reports_dir = Path(sys.argv[1])
    
    if not reports_dir.exists():
        print(f"ERROR: Reports directory not found: {reports_dir}")
        sys.exit(1)
    
    if not reports_dir.is_dir():
        print(f"ERROR: Not a directory: {reports_dir}")
        sys.exit(1)
    
    # Generate report
    report = generate_report(reports_dir)
    
    # Print to console
    print(report)
    
    # Save to file
    output_file = reports_dir / "performance_analysis.txt"
    with open(output_file, 'w') as f:
        f.write(report)
    
    print(f"\nReport saved to: {output_file}")


if __name__ == "__main__":
    main()
