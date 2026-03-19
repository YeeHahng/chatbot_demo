#!/usr/bin/env python3
"""
Benchmark script: runs test_cases.json against the running server.
Usage: python scripts/benchmark.py [--model MODEL] [--url URL]

Server must be running: uvicorn app.main:app --reload
"""
import sys
import json
import argparse
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx


def parse_args():
    parser = argparse.ArgumentParser(
        description="Benchmark the SkyView Property Bot webhook against test cases."
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name (display purposes only, does not override server config).",
    )
    parser.add_argument(
        "--url",
        type=str,
        default="http://localhost:8000",
        help="Base URL of the running server (default: http://localhost:8000).",
    )
    return parser.parse_args()


def load_test_cases() -> list[dict]:
    cases_path = Path(__file__).parent.parent / "eval" / "test_cases.json"
    with open(cases_path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_contains(reply: str, expected_contains: list[str]) -> tuple[bool, str]:
    """Return (passed, failure_reason). Checks are case-insensitive."""
    reply_lower = reply.lower()
    for term in expected_contains:
        if term.lower() not in reply_lower:
            return False, f"Expected '{term}' not found in reply"
    return True, ""


def check_intent(actual_intent: str, expected_intent: str | None) -> tuple[bool, str]:
    """Return (passed, failure_reason). Skips check if expected_intent is None."""
    if expected_intent is None:
        return True, ""
    if actual_intent != expected_intent:
        return False, f"Intent mismatch: got '{actual_intent}', expected '{expected_intent}'"
    return True, ""


def run_benchmark(url: str, model: str | None, test_cases: list[dict]) -> None:
    webhook_url = f"{url}/webhook"
    results = []

    print(f"Running benchmark against: {webhook_url}")
    if model:
        print(f"Model (display): {model}")
    print(f"Test cases: {len(test_cases)}")
    print("=" * 60)

    seed_url = f"{url}/seed"

    with httpx.Client(timeout=30.0) as client:
        for case in test_cases:
            tc_id = case["id"]
            question = case["question"]
            phone = case["phone"]
            expected_contains = case.get("expected_contains", [])
            expected_intent = case.get("expected_intent", None)

            question_snippet = question[:50] + "..." if len(question) > 50 else question

            # Pre-seed session state so BOOKED cases have building/unit context
            if case.get("building") or case.get("unit") or case.get("state", "UNKNOWN") != "UNKNOWN":
                client.post(seed_url, json={
                    "phone": phone,
                    "building": case.get("building"),
                    "unit": case.get("unit"),
                    "state": case.get("state", "UNKNOWN"),
                })

            start = time.monotonic()
            try:
                response = client.post(
                    webhook_url,
                    json={"phone": phone, "message": question},
                )
                elapsed_ms = int((time.monotonic() - start) * 1000)
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as exc:
                elapsed_ms = int((time.monotonic() - start) * 1000)
                reason = f"HTTP {exc.response.status_code}: {exc.response.text[:100]}"
                print(f"[FAIL] {tc_id} | {question_snippet} | {reason}")
                results.append(
                    {"id": tc_id, "passed": False, "reason": reason, "latency_ms": elapsed_ms}
                )
                continue
            except Exception as exc:
                elapsed_ms = int((time.monotonic() - start) * 1000)
                reason = f"Request error: {exc}"
                print(f"[FAIL] {tc_id} | {question_snippet} | {reason}")
                results.append(
                    {"id": tc_id, "passed": False, "reason": reason, "latency_ms": elapsed_ms}
                )
                continue

            reply = data.get("reply", "")
            actual_intent = data.get("intent", "")

            contains_ok, contains_reason = check_contains(reply, expected_contains)
            intent_ok, intent_reason = check_intent(actual_intent, expected_intent)

            passed = contains_ok and intent_ok
            failure_reason = " | ".join(filter(None, [contains_reason, intent_reason]))

            if passed:
                print(f"[PASS] {tc_id} | {question_snippet} | {elapsed_ms}ms")
            else:
                print(f"[FAIL] {tc_id} | {question_snippet} | {failure_reason} | {elapsed_ms}ms")

            results.append(
                {
                    "id": tc_id,
                    "passed": passed,
                    "reason": failure_reason,
                    "latency_ms": elapsed_ms,
                }
            )

    # Summary
    total = len(results)
    passed_count = sum(1 for r in results if r["passed"])
    failed_count = total - passed_count
    pass_pct = (passed_count / total * 100) if total > 0 else 0.0

    latencies = [r["latency_ms"] for r in results]
    avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0
    sorted_latencies = sorted(latencies)
    p95_index = int(len(sorted_latencies) * 0.95) - 1
    p95_index = max(0, p95_index)
    p95_latency = sorted_latencies[p95_index] if sorted_latencies else 0

    print()
    print("=" * 60)
    print("BENCHMARK RESULTS")
    print("=" * 60)
    print(f"Total:    {total}")
    print(f"Passed:   {passed_count}  ({pass_pct:.1f}%)")
    print(f"Failed:   {failed_count}")
    print()
    print(f"Avg latency:  {avg_latency}ms")
    print(f"P95 latency:  {p95_latency}ms")
    print("=" * 60)


def main():
    args = parse_args()
    test_cases = load_test_cases()
    run_benchmark(url=args.url, model=args.model, test_cases=test_cases)


if __name__ == "__main__":
    main()
