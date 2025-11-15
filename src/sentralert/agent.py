"""Main AlertAgent orchestrator for running analysis flows."""

from pathlib import Path

from .clients import ClaudeClient, SentryClient
from .flows import HistoricalAnalysisFlow


class AlertAgent:
    """
    Main orchestrator for alert analysis flows.

    The AlertAgent handles historical analysis of past Sentry metrics
    to propose reactive alerts. Service analysis is now handled by
    the ServiceAnalysisAgent (Claude Agent SDK) directly.
    """

    def __init__(
        self,
        sentry_client: SentryClient,
        claude_client: ClaudeClient,
        output_dir: str = "alerts",
    ):
        """
        Initialize the AlertAgent.

        Args:
            sentry_client: Client for querying Sentry metrics
            claude_client: Client for AI-powered analysis
            output_dir: Directory to save generated alert files
        """
        self.sentry = sentry_client
        self.claude = claude_client
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        # Initialize flow lazily to avoid requiring unnecessary configuration
        self._historical_flow = None

    @property
    def historical_flow(self):
        """Lazy initialization of historical analysis flow."""
        if self._historical_flow is None:
            self._historical_flow = HistoricalAnalysisFlow(self.sentry, self.claude)
        return self._historical_flow

    def run(self, flow: str = "historical") -> list[dict]:
        """
        Run historical alert analysis flow.

        Args:
            flow: Analysis flow ("historical" is the only supported value)

        Returns:
            List of alert suggestions from historical analysis
        """
        if flow != "historical":
            raise ValueError(
                f"Invalid flow '{flow}'. AlertAgent only supports 'historical'. "
                "Use ServiceAnalysisAgent for service/codebase analysis."
            )

        suggestions = self.historical_flow.analyze_and_propose()
        print(f"\nTotal suggestions: {len(suggestions)}")

        return suggestions

    def save_as_yaml(self, suggestions: list[dict]) -> list[Path]:
        """
        Save alert suggestions as YAML files.

        Args:
            suggestions: List of alert suggestion dictionaries

        Returns:
            List of paths to saved YAML files
        """
        import yaml

        saved_files = []

        for suggestion in suggestions:
            # Create filename from alert name
            name_slug = (
                suggestion["name"].lower().replace(" ", "-").replace("/", "-")
            )
            filename = self.output_dir / f"{name_slug}.yaml"

            # Add metadata
            suggestion["proposed_by"] = suggestion.get("flow", "unknown")

            with open(filename, "w") as f:
                yaml.dump(suggestion, f, default_flow_style=False, sort_keys=False)

            saved_files.append(filename)
            print(f"  Saved: {filename}")

        return saved_files
