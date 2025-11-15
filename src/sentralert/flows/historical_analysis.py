"""Historical metrics analysis flow for proposing reactive alerts."""

import json
import os

from ..clients.claude_client import ClaudeClient
from ..clients.sentry_client import SentryClient


class HistoricalAnalysisFlow:
    """
    Analyzes Sentry metrics from the past to propose reactive alerts.

    This flow examines historical data to identify patterns such as:
    - Latency regressions
    - Error rate spikes
    - High failure rates per transaction
    """

    def __init__(self, sentry_client: SentryClient, claude_client: ClaudeClient):
        """
        Initialize the historical analysis flow.

        Args:
            sentry_client: Client for querying Sentry metrics
            claude_client: Client for AI-powered analysis
        """
        self.sentry = sentry_client
        self.claude = claude_client

    def analyze_and_propose(self, environment: str = "production") -> list[dict]:
        """
        Main entry point for Flow 1 - Historical Metrics Analysis.

        Args:
            environment: Sentry environment to analyze

        Returns:
            List of alert suggestions
        """
        print("\n" + "=" * 70)
        print("FLOW 1: HISTORICAL METRICS ANALYSIS")
        print("=" * 70)

        suggestions = []

        # Analyze latency patterns
        print("\nAnalyzing transaction latency patterns...")
        latency_alerts = self._analyze_latency_regression(environment)
        suggestions.extend(latency_alerts)

        # Analyze error rates
        print("Analyzing error rate patterns...")
        error_alerts = self._analyze_error_rates(environment)
        suggestions.extend(error_alerts)

        # Analyze failure rates per transaction
        print("Analyzing failure rates per endpoint...")
        failure_alerts = self._analyze_failure_rates(environment)
        suggestions.extend(failure_alerts)

        return suggestions

    def _analyze_latency_regression(self, environment: str) -> list[dict]:
        """
        Detect p95 latency regressions.

        Args:
            environment: Sentry environment to analyze

        Returns:
            List of latency-related alert suggestions
        """
        # Get 7-day baseline
        baseline = self.sentry.discover(
            ["transaction", "p95(transaction.duration)", "count()"],
            f"event.type:transaction environment:{environment}",
            "7d",
        )

        # Get 1-hour current
        current = self.sentry.discover(
            ["transaction", "p95(transaction.duration)", "count()"],
            f"event.type:transaction environment:{environment}",
            "1h",
        )

        # Build baseline dict
        baseline_map = {
            row["transaction"]: row["p95(transaction.duration)"] for row in baseline
        }

        suggestions = []
        for row in current:
            tx = row["transaction"]
            p95_now = row["p95(transaction.duration)"]
            p95_base = baseline_map.get(tx)

            if p95_base and p95_now > 500 and p95_now > 1.4 * p95_base:
                # Ask Claude to validate and enrich
                prompt = f"""Analyze this latency regression:

TRANSACTION: {tx}
- Baseline p95 (7d): {p95_base:.0f}ms
- Current p95 (1h): {p95_now:.0f}ms
- Regression: {((p95_now/p95_base - 1) * 100):.1f}%

Respond with valid JSON only:
{{
  "alert_name": "brief descriptive name",
  "justification": "2-3 sentences explaining why this alert is needed",
  "severity": "LOW/MEDIUM/HIGH/CRITICAL",
  "warning_threshold_ms": <number>,
  "critical_threshold_ms": <number>,
  "is_legitimate": true/false
}}

Only mark is_legitimate=true if regression > 30% and current latency > 500ms.
"""

                try:
                    response = self.claude.analyze(prompt)
                    # Strip markdown
                    if "```json" in response:
                        response = response.split("```json")[1].split("```")[0].strip()
                    elif "```" in response:
                        response = response.split("```")[1].split("```")[0].strip()

                    analysis = json.loads(response)

                    if analysis.get("is_legitimate"):
                        suggestions.append(
                            {
                                "kind": "sentry.metric_alert",
                                "flow": "historical",
                                "name": analysis["alert_name"],
                                "dataset": "transactions",
                                "aggregate": "p95(transaction.duration)",
                                "query": f'event.type:transaction transaction:"{tx}" environment:{environment}',
                                "timeWindow": 5,
                                "thresholdType": "above",
                                "environment": environment,
                                "thresholds": {
                                    "warning": analysis["warning_threshold_ms"],
                                    "critical": analysis["critical_threshold_ms"],
                                },
                                "resolveThreshold": int(p95_base * 1.1),
                                "justification": analysis["justification"],
                                "severity": analysis["severity"],
                                "actions": [
                                    {
                                        "type": "email",
                                        "targetType": "specific",
                                        "targetIdentifier": os.getenv(
                                            "ALERTS_NOTIFY_EMAIL", "team@example.com"
                                        ),
                                    }
                                ],
                            }
                        )
                        print(f"  Proposed: {analysis['alert_name']}")
                    else:
                        print(f"  Skipped: {tx} (not significant enough)")

                except (json.JSONDecodeError, KeyError) as e:
                    print(f"  Failed to parse Claude response: {e}")

        return suggestions

    def _analyze_error_rates(self, environment: str) -> list[dict]:
        """
        Detect error rate spikes.

        Args:
            environment: Sentry environment to analyze

        Returns:
            List of error rate alert suggestions
        """
        # Get error counts for last hour
        errors = self.sentry.discover(
            ["count()"], f"event.type:error environment:{environment}", "1h"
        )

        if not errors:
            return []

        error_count = errors[0]["count()"]

        # Simple heuristic: > 50 errors/hour warrants an alert
        if error_count > 50:
            return [
                {
                    "kind": "sentry.metric_alert",
                    "flow": "historical",
                    "name": f"High error rate in {environment}",
                    "dataset": "events",
                    "aggregate": "count()",
                    "query": f"event.type:error environment:{environment}",
                    "timeWindow": 5,
                    "thresholdType": "above",
                    "environment": environment,
                    "thresholds": {"warning": 30, "critical": 50},
                    "justification": f"Detected {error_count} errors in the last hour, which exceeds normal baseline.",
                    "severity": "HIGH",
                    "actions": [
                        {
                            "type": "email",
                            "targetType": "specific",
                            "targetIdentifier": os.getenv(
                                "ALERTS_NOTIFY_EMAIL", "team@example.com"
                            ),
                        }
                    ],
                }
            ]

        return []

    def _analyze_failure_rates(self, environment: str) -> list[dict]:
        """
        Detect high failure rates per transaction.

        Args:
            environment: Sentry environment to analyze

        Returns:
            List of failure rate alert suggestions
        """
        failure_data = self.sentry.discover(
            ["transaction", "failure_rate()"],
            f"event.type:transaction environment:{environment}",
            "1h",
        )

        suggestions = []
        for row in failure_data:
            tx = row["transaction"]
            failure_rate = row["failure_rate()"]

            # Critical: > 5% failure rate
            if failure_rate > 0.05:
                suggestions.append(
                    {
                        "kind": "sentry.metric_alert",
                        "flow": "historical",
                        "name": f"{tx} high failure rate",
                        "dataset": "transactions",
                        "aggregate": "failure_rate()",
                        "query": f'event.type:transaction transaction:"{tx}" environment:{environment}',
                        "timeWindow": 5,
                        "thresholdType": "above",
                        "environment": environment,
                        "thresholds": {
                            "warning": 0.03,  # 3%
                            "critical": 0.05,  # 5%
                        },
                        "justification": f"Current failure rate is {failure_rate*100:.1f}%, which is critically high for a user-facing endpoint.",
                        "severity": "CRITICAL",
                        "actions": [
                            {
                                "type": "email",
                                "targetType": "specific",
                                "targetIdentifier": os.getenv(
                                    "ALERTS_NOTIFY_EMAIL", "team@example.com"
                                ),
                            }
                        ],
                    }
                )
                print(f"  Proposed: {tx} failure rate alert")

        return suggestions
