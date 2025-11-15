"""Sentry API client for querying metrics and events."""


import requests


class SentryClient:
    """Client for interacting with Sentry API to fetch metrics and events."""

    def __init__(self, auth_token: str, org_slug: str):
        """
        Initialize Sentry client.

        Args:
            auth_token: Sentry API authentication token
            org_slug: Organization slug in Sentry
        """
        self.base_url = "https://sentry.io/api/0"
        self.headers = {"Authorization": f"Bearer {auth_token}"}
        self.org = org_slug

    def discover(
        self, fields: list[str], query: str, stats_period: str = "1h"
    ) -> list[dict]:
        """
        Query Sentry Discover API for metrics.

        Args:
            fields: List of fields to retrieve
            query: Sentry query string
            stats_period: Time period for stats (e.g., "1h", "7d")

        Returns:
            List of event data dictionaries

        Raises:
            requests.HTTPError: If the API request fails
        """
        param_list = [
            ("statsPeriod", stats_period),
            ("query", query),
            ("per_page", 100),
        ]
        for field in fields:
            param_list.append(("field", field))

        response = requests.get(
            f"{self.base_url}/organizations/{self.org}/events/",
            params=param_list,
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json().get("data", [])
