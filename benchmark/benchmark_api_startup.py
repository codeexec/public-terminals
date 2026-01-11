#!/usr/bin/env python3
"""
Comprehensive benchmark script for measuring Terminal container startup time via API.

This script measures:
1. Total startup time (API call to tunnel URL ready)
2. Container creation time
3. Container start time
4. Terminado health check time
5. Tunnel URL acquisition time
6. API polling time

Usage:
    python benchmark_api_startup.py --iterations 10 --output results.json
"""

import argparse
import asyncio
import json
import time
from datetime import datetime
from typing import Dict, List, Optional
import statistics
import httpx
import subprocess
import sys


class TerminalStartupBenchmark:
    def __init__(self, api_url: str = "http://localhost:8000"):
        self.api_url = api_url
        self.api_base = f"{api_url}/api/v1"
        self.client = httpx.AsyncClient(timeout=180.0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def measure_startup(self) -> Dict[str, float]:
        """Measure a single terminal startup and return timing breakdown."""
        timings = {
            "start_time": time.time(),
            "api_call_start": None,
            "api_call_end": None,
            "container_id": None,
            "terminal_id": None,
            "container_created": None,
            "container_started": None,
            "tunnel_url_ready": None,
            "total_time": None,
        }

        # 1. Create terminal via API
        timings["api_call_start"] = time.time()
        try:
            response = await self.client.post(f"{self.api_base}/terminals", json={})
            response.raise_for_status()
            terminal_data = response.json()
            timings["terminal_id"] = terminal_data.get("id")
            timings["api_call_end"] = time.time()

            print(f"  Terminal {timings['terminal_id']} created at t={timings['api_call_end'] - timings['start_time']:.3f}s")

        except Exception as e:
            print(f"  ERROR: Failed to create terminal: {e}")
            return timings

        # 2. Poll for terminal to become ready
        max_wait = 120  # 2 minutes max
        poll_interval = 0.5  # Poll every 500ms
        start_polling = time.time()

        while time.time() - start_polling < max_wait:
            try:
                response = await self.client.get(f"{self.api_base}/terminals/{timings['terminal_id']}")
                response.raise_for_status()
                terminal = response.json()

                status = terminal.get("status")
                tunnel_url = terminal.get("tunnel_url")
                container_id = terminal.get("container_id")

                # Track when container was first seen
                if container_id and not timings["container_id"]:
                    timings["container_id"] = container_id
                    timings["container_created"] = time.time()
                    print(f"  Container {container_id[:12]} detected at t={timings['container_created'] - timings['start_time']:.3f}s")

                # Track status transitions
                if status == "STARTING" and not timings["container_started"]:
                    timings["container_started"] = time.time()
                    print(f"  Status STARTING at t={timings['container_started'] - timings['start_time']:.3f}s")

                if status == "STARTED" and tunnel_url:
                    timings["tunnel_url_ready"] = time.time()
                    timings["total_time"] = timings["tunnel_url_ready"] - timings["start_time"]
                    print(f"  Tunnel URL ready at t={timings['total_time']:.3f}s")
                    print(f"  Total startup time: {timings['total_time']:.3f}s")
                    break

            except Exception as e:
                print(f"  Polling error: {e}")

            await asyncio.sleep(poll_interval)

        # Cleanup
        if timings["terminal_id"]:
            try:
                await self.client.delete(f"{self.api_base}/terminals/{timings['terminal_id']}")
                print(f"  Cleaned up terminal {timings['terminal_id']}")
            except Exception as e:
                print(f"  Cleanup error: {e}")

        return timings

    async def run_benchmark(self, iterations: int = 10, delay_between: int = 5) -> List[Dict[str, float]]:
        """Run multiple startup measurements."""
        results = []

        print(f"\nStarting benchmark with {iterations} iterations...")
        print(f"API URL: {self.api_url}")
        print("=" * 80)

        for i in range(iterations):
            print(f"\n[Iteration {i + 1}/{iterations}]")
            timings = await self.measure_startup()
            results.append(timings)

            # Wait between iterations to avoid overloading
            if i < iterations - 1:
                print(f"  Waiting {delay_between}s before next iteration...")
                await asyncio.sleep(delay_between)

        return results


def analyze_results(results: List[Dict[str, float]]) -> Dict:
    """Analyze benchmark results and compute statistics."""
    total_times = [r["total_time"] for r in results if r.get("total_time")]
    api_call_times = [
        r["api_call_end"] - r["api_call_start"]
        for r in results
        if r.get("api_call_start") and r.get("api_call_end")
    ]
    container_creation_times = [
        r["container_created"] - r["start_time"]
        for r in results
        if r.get("container_created")
    ]
    tunnel_acquisition_times = [
        r["tunnel_url_ready"] - r["container_created"]
        for r in results
        if r.get("tunnel_url_ready") and r.get("container_created")
    ]

    analysis = {
        "timestamp": datetime.now().isoformat(),
        "iterations": len(results),
        "successful": len(total_times),
        "failed": len(results) - len(total_times),
        "total_startup_time": {
            "min": min(total_times) if total_times else None,
            "max": max(total_times) if total_times else None,
            "mean": statistics.mean(total_times) if total_times else None,
            "median": statistics.median(total_times) if total_times else None,
            "stdev": statistics.stdev(total_times) if len(total_times) > 1 else None,
            "p95": sorted(total_times)[int(len(total_times) * 0.95)] if total_times else None,
            "p99": sorted(total_times)[int(len(total_times) * 0.99)] if total_times else None,
        },
        "api_call_time": {
            "mean": statistics.mean(api_call_times) if api_call_times else None,
            "median": statistics.median(api_call_times) if api_call_times else None,
        },
        "container_creation_time": {
            "mean": statistics.mean(container_creation_times) if container_creation_times else None,
            "median": statistics.median(container_creation_times) if container_creation_times else None,
        },
        "tunnel_acquisition_time": {
            "mean": statistics.mean(tunnel_acquisition_times) if tunnel_acquisition_times else None,
            "median": statistics.median(tunnel_acquisition_times) if tunnel_acquisition_times else None,
        },
        "raw_results": results,
    }

    return analysis


def print_summary(analysis: Dict):
    """Print a human-readable summary of the benchmark results."""
    print("\n" + "=" * 80)
    print("BENCHMARK SUMMARY")
    print("=" * 80)
    print(f"\nTimestamp: {analysis['timestamp']}")
    print(f"Total iterations: {analysis['iterations']}")
    print(f"Successful: {analysis['successful']}")
    print(f"Failed: {analysis['failed']}")

    if analysis['total_startup_time']['mean']:
        print(f"\nTotal Startup Time:")
        print(f"  Mean:   {analysis['total_startup_time']['mean']:.3f}s")
        print(f"  Median: {analysis['total_startup_time']['median']:.3f}s")
        print(f"  Min:    {analysis['total_startup_time']['min']:.3f}s")
        print(f"  Max:    {analysis['total_startup_time']['max']:.3f}s")
        if analysis['total_startup_time']['stdev']:
            print(f"  StdDev: {analysis['total_startup_time']['stdev']:.3f}s")
        print(f"  P95:    {analysis['total_startup_time']['p95']:.3f}s")
        print(f"  P99:    {analysis['total_startup_time']['p99']:.3f}s")

    if analysis['api_call_time']['mean']:
        print(f"\nAPI Call Time:")
        print(f"  Mean:   {analysis['api_call_time']['mean']:.3f}s")
        print(f"  Median: {analysis['api_call_time']['median']:.3f}s")

    if analysis['container_creation_time']['mean']:
        print(f"\nContainer Creation Time (from start to container detected):")
        print(f"  Mean:   {analysis['container_creation_time']['mean']:.3f}s")
        print(f"  Median: {analysis['container_creation_time']['median']:.3f}s")

    if analysis['tunnel_acquisition_time']['mean']:
        print(f"\nTunnel Acquisition Time (from container created to URL ready):")
        print(f"  Mean:   {analysis['tunnel_acquisition_time']['mean']:.3f}s")
        print(f"  Median: {analysis['tunnel_acquisition_time']['median']:.3f}s")

    print("\n" + "=" * 80)


async def main():
    parser = argparse.ArgumentParser(description="Benchmark Terminal container startup time")
    parser.add_argument(
        "--iterations", "-n",
        type=int,
        default=10,
        help="Number of startup iterations to measure (default: 10)"
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default="http://localhost:8000",
        help="API base URL (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="benchmark_results.json",
        help="Output file for results (default: benchmark_results.json)"
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=5,
        help="Delay between iterations in seconds (default: 5)"
    )

    args = parser.parse_args()

    # Run benchmark
    async with TerminalStartupBenchmark(api_url=args.api_url) as benchmark:
        results = await benchmark.run_benchmark(
            iterations=args.iterations,
            delay_between=args.delay
        )

    # Analyze results
    analysis = analyze_results(results)

    # Print summary
    print_summary(analysis)

    # Save to file
    with open(args.output, 'w') as f:
        json.dump(analysis, f, indent=2)

    print(f"\nResults saved to {args.output}")

    # Return exit code based on success rate
    if analysis['failed'] > 0:
        print(f"\nWARNING: {analysis['failed']} iterations failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
