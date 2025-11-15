#!/usr/bin/env python3
"""Script to apply Sentry alerts from YAML files to Sentry organization."""

import os
import sys
import glob
import yaml
import requests
from pathlib import Path
from typing import Any, Dict, List


class SentryAlertApplier:
    """Applies alert configurations to Sentry via API."""

    def __init__(self, auth_token: str, org_slug: str, api_url: str = "https://sentry.io/api/0"):
        """
        Initialize the Sentry alert applier.

        Args:
            auth_token: Sentry API authentication token
            org_slug: Organization slug in Sentry
            api_url: Base URL for Sentry API
        """
        self.api_url = api_url
        self.org_slug = org_slug
        self.headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        }

    def get_projects(self) -> List[Dict[str, Any]]:
        """Get all projects in the organization."""
        url = f"{self.api_url}/organizations/{self.org_slug}/projects/"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def get_project_by_environment(self, environment: str) -> str:
        """
        Get project slug for a given environment.

        Args:
            environment: Environment name (e.g., 'production', 'staging')

        Returns:
            Project slug, defaults to first project if not found
        """
        projects = self.get_projects()
        if not projects:
            raise ValueError("No projects found in organization")

        # For now, use the first project
        # In a real scenario, you'd want to map environments to projects
        return projects[0]["slug"]

    def list_existing_alerts(self, project_slug: str) -> List[Dict[str, Any]]:
        """
        List all existing metric alerts for a project.

        Args:
            project_slug: Project slug

        Returns:
            List of existing alert rules
        """
        url = f"{self.api_url}/projects/{self.org_slug}/{project_slug}/alert-rules/"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def find_alert_by_name(self, project_slug: str, alert_name: str) -> Dict[str, Any] | None:
        """
        Find an existing alert by name.

        Args:
            project_slug: Project slug
            alert_name: Name of the alert to find

        Returns:
            Alert rule if found, None otherwise
        """
        existing_alerts = self.list_existing_alerts(project_slug)
        for alert in existing_alerts:
            if alert.get("name") == alert_name:
                return alert
        return None

    def map_dataset(self, dataset: str) -> str:
        """
        Map YAML dataset to Sentry dataset.

        Args:
            dataset: Dataset from YAML (e.g., 'transactions', 'errors')

        Returns:
            Sentry dataset identifier
        """
        dataset_mapping = {
            "transactions": "transactions",
            "errors": "errors",
            "sessions": "sessions",
        }
        return dataset_mapping.get(dataset, "transactions")

    def map_aggregate(self, aggregate: str) -> str:
        """
        Map YAML aggregate to Sentry aggregate format.

        Args:
            aggregate: Aggregate function from YAML

        Returns:
            Sentry-compatible aggregate string
        """
        # Sentry aggregates are already in the correct format
        # e.g., "p95(transaction.duration)", "count()", "failure_rate()"
        return aggregate

    def create_or_update_alert(self, alert_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create or update a metric alert in Sentry.

        Args:
            alert_config: Alert configuration from YAML

        Returns:
            Created or updated alert rule
        """
        environment = alert_config.get("environment", "production")
        project_slug = self.get_project_by_environment(environment)

        # Check if alert already exists
        existing_alert = self.find_alert_by_name(project_slug, alert_config["name"])

        # Build the alert rule payload
        payload = self._build_alert_payload(alert_config, project_slug)

        if existing_alert:
            # Update existing alert
            url = f"{self.api_url}/projects/{self.org_slug}/{project_slug}/alert-rules/{existing_alert['id']}/"
            response = requests.put(url, json=payload, headers=self.headers)
            print(f"Updated alert: {alert_config['name']}")
        else:
            # Create new alert
            url = f"{self.api_url}/projects/{self.org_slug}/{project_slug}/alert-rules/"
            response = requests.post(url, json=payload, headers=self.headers)
            print(f"Created alert: {alert_config['name']}")

        response.raise_for_status()
        return response.json()

    def _build_alert_payload(self, alert_config: Dict[str, Any], project_slug: str) -> Dict[str, Any]:
        """
        Build Sentry API payload from alert configuration.

        Args:
            alert_config: Alert configuration from YAML
            project_slug: Project slug

        Returns:
            Sentry API payload
        """
        thresholds = alert_config.get("thresholds", {})
        threshold_type = alert_config.get("thresholdType", "above")

        # Map threshold type to Sentry's format (0 = above, 1 = below)
        threshold_type_value = 0 if threshold_type == "above" else 1

        # Build triggers (warning and critical)
        triggers = []

        # Critical trigger (required)
        if "critical" in thresholds:
            triggers.append({
                "label": "critical",
                "alertThreshold": thresholds["critical"],
                "actions": self._build_actions(alert_config),
            })

        # Warning trigger (optional)
        if "warning" in thresholds:
            triggers.append({
                "label": "warning",
                "alertThreshold": thresholds["warning"],
                "actions": self._build_actions(alert_config),
            })

        payload = {
            "name": alert_config["name"],
            "dataset": self.map_dataset(alert_config.get("dataset", "transactions")),
            "query": alert_config.get("query", ""),
            "aggregate": self.map_aggregate(alert_config.get("aggregate", "count()")),
            "timeWindow": alert_config.get("timeWindow", 5),
            "thresholdType": threshold_type_value,
            "triggers": triggers,
            "projects": [project_slug],
        }

        # Add environment filter if specified
        if "environment" in alert_config:
            payload["environment"] = alert_config["environment"]

        return payload

    def _build_actions(self, alert_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Build action configurations for alert triggers.

        Args:
            alert_config: Alert configuration from YAML

        Returns:
            List of action configurations
        """
        actions = []
        action_configs = alert_config.get("actions", [])

        for action_config in action_configs:
            action_type = action_config.get("type", "email")

            if action_type == "email":
                target_type = action_config.get("targetType", "specific")
                target_identifier = action_config.get("targetIdentifier", "")

                # Map target type to Sentry format
                if target_type == "specific":
                    actions.append({
                        "type": "email",
                        "targetType": "specific",
                        "targetIdentifier": target_identifier,
                    })
                elif target_type == "team":
                    actions.append({
                        "type": "email",
                        "targetType": "team",
                        "targetIdentifier": target_identifier,
                    })

        return actions

    def apply_alerts_from_directory(self, alerts_dir: str) -> List[Dict[str, Any]]:
        """
        Apply all alerts from YAML files in a directory.

        Args:
            alerts_dir: Directory containing alert YAML files

        Returns:
            List of created/updated alert rules
        """
        alerts_path = Path(alerts_dir)
        if not alerts_path.exists():
            print(f"Alerts directory not found: {alerts_dir}")
            return []

        # Find all YAML files
        yaml_files = list(alerts_path.glob("*.yaml")) + list(alerts_path.glob("*.yml"))

        if not yaml_files:
            print(f"No YAML files found in {alerts_dir}")
            return []

        results = []
        for yaml_file in yaml_files:
            print(f"\nProcessing {yaml_file.name}...")
            try:
                with open(yaml_file, "r") as f:
                    alert_config = yaml.safe_load(f)

                # Skip if not a metric alert
                if alert_config.get("kind") != "sentry.metric_alert":
                    print(f"Skipping {yaml_file.name} - not a metric alert")
                    continue

                result = self.create_or_update_alert(alert_config)
                results.append(result)

            except Exception as e:
                print(f"Error processing {yaml_file.name}: {e}")
                # Continue processing other files
                continue

        return results


def main():
    """Main entry point for the script."""
    # Get configuration from environment variables
    auth_token = os.getenv("SENTRY_AUTH_TOKEN")
    org_slug = os.getenv("SENTRY_ORG_SLUG")
    api_url = os.getenv("SENTRY_API", "https://sentry.io/api/0")

    if not auth_token or not org_slug:
        print("Error: SENTRY_AUTH_TOKEN and SENTRY_ORG_SLUG must be set")
        sys.exit(1)

    # Get alerts directory from command line argument
    if len(sys.argv) < 2:
        print("Usage: python apply_alerts.py <alerts_directory>")
        sys.exit(1)

    alerts_dir = sys.argv[1]

    # Initialize applier and apply alerts
    applier = SentryAlertApplier(auth_token, org_slug, api_url)

    print(f"Applying alerts from {alerts_dir} to Sentry organization: {org_slug}")
    print("=" * 80)

    try:
        results = applier.apply_alerts_from_directory(alerts_dir)
        print("\n" + "=" * 80)
        print(f"Successfully processed {len(results)} alert(s)")
        sys.exit(0)
    except Exception as e:
        print(f"\nFatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
