"""Service Analysis Agent using Claude Agent SDK."""

import json
from typing import Any

from anthropic import Anthropic

from ..clients.sentry_client import SentryClient
from .tools import create_deepwiki_tool_definition, create_sentry_traces_tool_definition


class ServiceAnalysisAgent:
    """
    Agent that analyzes services by combining codebase insights from deepwiki
    with actual production traces from Sentry to propose intelligent alerts.

    Uses Claude Agent SDK with Haiku 4.5 for cost-effective analysis.
    """

    def __init__(
        self,
        anthropic_api_key: str,
        sentry_client: SentryClient,
        deepwiki_repo_url: str = "https://deepwiki.com/wuTims/sentralert-demo-service",
    ):
        """
        Initialize the service analysis agent.

        Args:
            anthropic_api_key: Anthropic API key for Claude
            sentry_client: Configured SentryClient instance
            deepwiki_repo_url: URL to the deepwiki repository
        """
        self.client = Anthropic(api_key=anthropic_api_key)
        self.model = "claude-haiku-4-5-20251001"
        self.sentry_client = sentry_client
        self.deepwiki_repo_url = deepwiki_repo_url

        # Initialize tools
        self.tools = self._create_tools()

    def _create_tools(self) -> list[dict[str, Any]]:
        """
        Create tool definitions for the agent.

        Returns:
            List of tool definitions
        """
        deepwiki_tool = create_deepwiki_tool_definition(self.deepwiki_repo_url)
        sentry_tool = create_sentry_traces_tool_definition(self.sentry_client)

        # Return tool definitions in Claude API format
        return [
            {
                "name": deepwiki_tool["name"],
                "description": deepwiki_tool["description"],
                "input_schema": deepwiki_tool["input_schema"],
            },
            {
                "name": sentry_tool["name"],
                "description": sentry_tool["description"],
                "input_schema": sentry_tool["input_schema"],
            },
        ]

    def _get_tool_function(self, tool_name: str):
        """
        Get the actual tool function by name.

        Args:
            tool_name: Name of the tool

        Returns:
            Callable tool function
        """
        if tool_name == "query_deepwiki_codebase":
            tool_def = create_deepwiki_tool_definition(self.deepwiki_repo_url)
            return tool_def["function"]
        elif tool_name == "query_sentry_traces":
            tool_def = create_sentry_traces_tool_definition(self.sentry_client)
            return tool_def["function"]
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    def _execute_tool(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """
        Execute a tool with given input.

        Args:
            tool_name: Name of the tool to execute
            tool_input: Input parameters for the tool

        Returns:
            Tool execution result as JSON string
        """
        tool_func = self._get_tool_function(tool_name)
        return tool_func(**tool_input)

    def analyze(
        self,
        analysis_type: str = "comprehensive",
        focus_endpoint: str = None,
    ) -> dict[str, Any]:
        """
        Run service analysis using the agent.

        The agent will autonomously:
        1. Query deepwiki to understand the codebase structure
        2. Query Sentry to get actual production metrics
        3. Synthesize insights to propose intelligent alerts

        Args:
            analysis_type: Type of analysis ("comprehensive", "endpoint-specific", "quick")
            focus_endpoint: Specific endpoint to focus on (optional)

        Returns:
            Dictionary containing:
            - suggestions: List of alert suggestions
            - insights: Analysis insights
            - execution_trace: Tool calls and responses
        """
        # Build the analysis prompt
        if analysis_type == "comprehensive":
            prompt = self._build_comprehensive_prompt()
        elif analysis_type == "endpoint-specific" and focus_endpoint:
            prompt = self._build_endpoint_prompt(focus_endpoint)
        else:
            prompt = self._build_quick_prompt()

        # Run the agent loop
        messages = [{"role": "user", "content": prompt}]
        execution_trace = []
        max_iterations = 10
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # Call Claude with tools
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                tools=self.tools,
                messages=messages,
            )

            # Check if we're done
            if response.stop_reason == "end_turn":
                # Extract final response
                final_content = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        final_content += block.text

                # Parse and return results
                return self._parse_final_response(final_content, execution_trace)

            # Handle tool use
            if response.stop_reason == "tool_use":
                # Add assistant message to conversation
                messages.append({"role": "assistant", "content": response.content})

                # Execute all tool calls
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input

                        print(f"  Agent calling tool: {tool_name}")
                        print(f"    Input: {json.dumps(tool_input, indent=2)}")

                        # Execute the tool
                        result = self._execute_tool(tool_name, tool_input)

                        # Record execution
                        execution_trace.append(
                            {
                                "iteration": iteration,
                                "tool": tool_name,
                                "input": tool_input,
                                "output": json.loads(result),
                            }
                        )

                        # Add to tool results
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result,
                            }
                        )

                # Add tool results to conversation
                messages.append({"role": "user", "content": tool_results})
            else:
                # Unexpected stop reason
                break

        # If we hit max iterations, return what we have
        return {
            "error": "Max iterations reached",
            "execution_trace": execution_trace,
            "suggestions": [],
        }

    def _build_comprehensive_prompt(self) -> str:
        """Build prompt for comprehensive service analysis."""
        return """You are a service analysis agent. Your task is to analyze a production service by combining codebase insights with actual production metrics to propose intelligent monitoring alerts.

Follow this process:

1. **Discover the codebase**: Use query_deepwiki_codebase to understand:
   - What API endpoints exist
   - What services and dependencies are present
   - Any potential issues identified in the code

2. **Analyze production behavior**: Use query_sentry_traces to examine:
   - Which endpoints are currently monitored vs unmonitored
   - Performance characteristics (p50, p95 latency)
   - Error rates and failure patterns
   - Recent error events

3. **Synthesize insights**: Compare codebase analysis with production data to identify:
   - Critical unmonitored endpoints (especially payment, checkout, refund)
   - Endpoints with concerning performance patterns
   - Services calling external APIs without proper monitoring
   - Database operations without timeout alerts

4. **Propose alerts**: For each issue found, propose a Sentry metric alert with:
   - Clear justification based on both code and production data
   - Appropriate thresholds based on actual metrics
   - Proper severity level
   - Specific metric to monitor (p95, failure_rate, error_count, etc.)

**Output Format**: Provide your final analysis as a JSON object with this structure:
```json
{
  "analysis_summary": "Brief summary of findings",
  "alerts": [
    {
      "endpoint": "POST /api/checkout",
      "alert_name": "Checkout failure rate critical",
      "justification": "Codebase shows external payment API call without error handling. Production data shows 2.5% failure rate.",
      "alert_config": {
        "aggregate": "failure_rate()",
        "warning_threshold": 1.0,
        "critical_threshold": 2.0,
        "severity": "CRITICAL",
        "time_window": 5
      }
    }
  ],
  "insights": {
    "unmonitored_count": 3,
    "critical_endpoints": ["POST /api/checkout", "POST /api/refund"],
    "recommendations": ["Add timeout monitoring for PaymentService calls"]
  }
}
```

Begin your analysis now."""

    def _build_endpoint_prompt(self, endpoint: str) -> str:
        """Build prompt for endpoint-specific analysis."""
        return f"""Analyze the specific endpoint: {endpoint}

1. Use query_deepwiki_codebase to understand this endpoint's implementation
2. Use query_sentry_traces to get its production metrics
3. Propose appropriate monitoring alerts based on the analysis

Provide response in JSON format with alert configuration."""

    def _build_quick_prompt(self) -> str:
        """Build prompt for quick analysis."""
        return """Perform a quick service analysis:

1. Query deepwiki for critical endpoints (payment, checkout, refund)
2. Query Sentry for their current monitoring status
3. Propose alerts for any unmonitored critical endpoints

Provide response in JSON format."""

    def _parse_final_response(
        self, response_text: str, execution_trace: list[dict]
    ) -> dict[str, Any]:
        """
        Parse the agent's final response into structured format.

        Args:
            response_text: Final text response from agent
            execution_trace: List of tool executions

        Returns:
            Structured analysis results
        """
        try:
            # Try to extract JSON from the response
            if "```json" in response_text:
                json_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_text = response_text.split("```")[1].split("```")[0].strip()
            else:
                json_text = response_text

            analysis = json.loads(json_text)

            # Convert to Sentry alert format
            suggestions = []
            for alert in analysis.get("alerts", []):
                config = alert.get("alert_config", {})
                suggestions.append(
                    {
                        "kind": "sentry.metric_alert",
                        "flow": "service_analysis_agent",
                        "name": alert.get("alert_name"),
                        "dataset": (
                            "transactions"
                            if "transaction.duration" in config.get("aggregate", "")
                            else "events"
                        ),
                        "aggregate": config.get("aggregate"),
                        "query": f'event.type:transaction transaction:"{alert.get("endpoint")}" environment:production',
                        "timeWindow": config.get("time_window", 5),
                        "thresholdType": "above",
                        "environment": "production",
                        "thresholds": {
                            "warning": config.get("warning_threshold"),
                            "critical": config.get("critical_threshold"),
                        },
                        "justification": alert.get("justification"),
                        "severity": config.get("severity", "HIGH"),
                        "actions": [
                            {
                                "type": "email",
                                "targetType": "specific",
                                "targetIdentifier": "team@example.com",
                            }
                        ],
                    }
                )

            return {
                "suggestions": suggestions,
                "insights": analysis.get("insights", {}),
                "analysis_summary": analysis.get("analysis_summary"),
                "execution_trace": execution_trace,
            }

        except (json.JSONDecodeError, KeyError, AttributeError) as e:
            # Fallback: return raw response
            return {
                "error": f"Failed to parse response: {str(e)}",
                "raw_response": response_text,
                "execution_trace": execution_trace,
                "suggestions": [],
            }

    def run_and_format(self, analysis_type: str = "comprehensive") -> list[dict]:
        """
        Run analysis and return formatted alert suggestions.

        Args:
            analysis_type: Type of analysis to run

        Returns:
            List of alert suggestion dictionaries in Sentry format
        """
        print("\n" + "=" * 70)
        print("SERVICE ANALYSIS AGENT (Claude Agent SDK)")
        print("=" * 70)
        print(f"Model: {self.model}")
        print(f"Analysis type: {analysis_type}")
        print(f"deepwiki repo: {self.deepwiki_repo_url}")
        print()

        result = self.analyze(analysis_type=analysis_type)

        if "error" in result:
            print(f"\nError: {result['error']}")
            if "raw_response" in result:
                print(f"Raw response: {result['raw_response']}")
        else:
            print("\nAnalysis complete!")
            print(f"  Summary: {result.get('analysis_summary')}")
            print(f"  Proposed alerts: {len(result['suggestions'])}")
            print(f"  Tool calls made: {len(result['execution_trace'])}")

        return result.get("suggestions", [])
