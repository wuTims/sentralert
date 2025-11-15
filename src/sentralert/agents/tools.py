"""Tools for the service analysis agent."""

import asyncio
import json
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client

from ..clients.sentry_client import SentryClient


class DeepWikiTool:
    """Tool for querying deepwiki MCP server for codebase insights using the Model Context Protocol."""

    def __init__(self, repo_url: str = "https://deepwiki.com/wuTims/sentralert-demo-service"):
        """
        Initialize deepwiki MCP tool.

        Args:
            repo_url: URL to the deepwiki repository (e.g., "https://deepwiki.com/owner/repo")
        """
        self.repo_url = repo_url
        # Extract repo path (e.g., "owner/repo" from "https://deepwiki.com/owner/repo")
        self.repo = repo_url.replace("https://deepwiki.com/", "")
        # DeepWiki MCP server endpoint
        self.mcp_server_url = "https://mcp.deepwiki.com/sse"

    async def _query_async(self, query: str) -> str:
        """
        Async implementation of deepwiki MCP query.

        Args:
            query: Natural language query about the codebase

        Returns:
            JSON string with codebase insights
        """
        try:
            # Connect to DeepWiki MCP server via SSE transport
            async with sse_client(self.mcp_server_url) as (read, write):
                async with ClientSession(read, write) as session:
                    # Initialize the MCP session
                    await session.initialize()

                    # Call the ask_question tool provided by DeepWiki MCP
                    result = await session.call_tool(
                        "ask_question",
                        arguments={
                            "repo": self.repo,
                            "question": query,
                        },
                    )

                    # Extract the response content
                    response_text = result.content[0].text if result.content else "{}"

                    # Try to parse as JSON, or wrap in structured format
                    try:
                        # If response is already JSON, parse and re-structure
                        data = json.loads(response_text)
                        structured_result = {
                            "query": query,
                            "codebase_insights": data,
                            "metadata": {
                                "repo": self.repo,
                                "source": "deepwiki_mcp",
                            },
                        }
                    except json.JSONDecodeError:
                        # If response is plain text, structure it
                        structured_result = {
                            "query": query,
                            "codebase_insights": {
                                "analysis": response_text,
                            },
                            "metadata": {
                                "repo": self.repo,
                                "source": "deepwiki_mcp",
                            },
                        }

                    return json.dumps(structured_result, indent=2)

        except Exception as e:
            # Fallback to mock data for development/testing when MCP connection fails
            return json.dumps(
                {
                    "query": query,
                    "codebase_insights": {
                        "endpoints": [
                            {
                                "path": "/api/checkout",
                                "method": "POST",
                                "description": "Process customer checkout",
                                "monitored": False,
                            },
                            {
                                "path": "/api/refund",
                                "method": "POST",
                                "description": "Process refund requests",
                                "monitored": False,
                            },
                            {
                                "path": "/api/orders/{id}",
                                "method": "GET",
                                "description": "Retrieve order details",
                                "monitored": True,
                            },
                        ],
                        "services": [
                            {"name": "PaymentService", "external_api": True},
                            {"name": "OrderService", "database": "postgresql"},
                        ],
                        "code_structure": {
                            "framework": "FastAPI",
                            "language": "Python",
                            "api_version": "v1",
                        },
                        "dependencies": ["stripe", "postgresql", "redis"],
                        "potential_issues": [
                            "No error handling on /api/checkout payment processing",
                            "Missing timeout configuration for external API calls",
                        ],
                    },
                    "metadata": {
                        "repo": self.repo,
                        "note": f"Mock data (MCP connection failed: {str(e)})",
                        "source": "fallback_mock",
                    },
                },
                indent=2,
            )

    def __call__(self, query: str) -> str:
        """
        Query deepwiki MCP server for codebase information.

        This is a synchronous wrapper around the async MCP client.

        Args:
            query: Natural language query about the codebase

        Returns:
            JSON string with codebase insights including:
            - endpoints: List of API endpoints found
            - services: Services and their dependencies
            - code_structure: Code organization details
            - potential_issues: Identified potential issues
        """
        # Run the async query in a new event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're already in an async context, create a new loop
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self._query_async(query))
                    return future.result()
            else:
                return loop.run_until_complete(self._query_async(query))
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(self._query_async(query))


class SentryTracesTool:
    """Tool for querying Sentry API for service traces and metrics."""

    def __init__(self, sentry_client: SentryClient):
        """
        Initialize Sentry traces tool.

        Args:
            sentry_client: Configured SentryClient instance
        """
        self.sentry = sentry_client

    def __call__(
        self, endpoint_path: str = None, stats_period: str = "24h", include_errors: bool = True
    ) -> str:
        """
        Query Sentry for traces and metrics for specific endpoint or all endpoints.

        Args:
            endpoint_path: Specific endpoint path to query (e.g., "POST /api/checkout")
                          If None, queries all endpoints
            stats_period: Time period for stats (e.g., "1h", "24h", "7d")
            include_errors: Whether to include error events

        Returns:
            JSON string with trace data including:
            - transactions: List of transaction traces
            - metrics: Performance metrics (p50, p95, error rate)
            - errors: Recent error events (if include_errors=True)
        """
        try:
            # Build query
            if endpoint_path:
                query = f'event.type:transaction transaction:"{endpoint_path}"'
            else:
                query = "event.type:transaction"

            # Fetch transaction data
            fields = [
                "transaction",
                "p50(transaction.duration)",
                "p95(transaction.duration)",
                "count()",
                "failure_rate()",
            ]
            transactions = self.sentry.discover(fields=fields, query=query, stats_period=stats_period)

            # Fetch error data if requested
            errors = []
            if include_errors:
                error_query = f'event.type:error {f"transaction:{endpoint_path}" if endpoint_path else ""}'
                error_fields = ["title", "count()", "last_seen()"]
                errors = self.sentry.discover(
                    fields=error_fields, query=error_query, stats_period=stats_period
                )

            # Structure the response
            result = {
                "query": {
                    "endpoint": endpoint_path or "all",
                    "period": stats_period,
                },
                "transactions": [
                    {
                        "name": tx.get("transaction"),
                        "metrics": {
                            "p50_duration_ms": tx.get("p50(transaction.duration)"),
                            "p95_duration_ms": tx.get("p95(transaction.duration)"),
                            "count": tx.get("count()"),
                            "failure_rate": tx.get("failure_rate()"),
                        },
                    }
                    for tx in transactions
                ],
                "errors": [
                    {
                        "title": err.get("title"),
                        "count": err.get("count()"),
                        "last_seen": err.get("last_seen()"),
                    }
                    for err in errors
                ],
                "summary": {
                    "total_transactions": len(transactions),
                    "total_errors": len(errors),
                    "monitored": len(transactions) > 0,
                },
            }

            return json.dumps(result, indent=2)

        except Exception as e:
            return json.dumps(
                {
                    "error": f"Failed to query Sentry: {str(e)}",
                    "query": {"endpoint": endpoint_path or "all", "period": stats_period},
                },
                indent=2,
            )


def create_deepwiki_tool_definition(repo_url: str) -> dict[str, Any]:
    """
    Create tool definition for deepwiki MCP query.

    Args:
        repo_url: URL to the deepwiki repository

    Returns:
        Tool definition dictionary for Claude Agent SDK
    """
    tool = DeepWikiTool(repo_url)

    return {
        "name": "query_deepwiki_codebase",
        "description": (
            "Query the deepwiki MCP server to get insights about the application codebase. "
            "Use this to discover endpoints, services, dependencies, and potential issues. "
            "Returns structured JSON with codebase information including API endpoints, "
            "service architecture, and code organization."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Natural language query about the codebase. Examples: "
                        "'What API endpoints exist?', 'Show me payment-related services', "
                        "'What are the external dependencies?'"
                    ),
                }
            },
            "required": ["query"],
        },
        "function": tool,
    }


def create_sentry_traces_tool_definition(sentry_client: SentryClient) -> dict[str, Any]:
    """
    Create tool definition for Sentry traces query.

    Args:
        sentry_client: Configured SentryClient instance

    Returns:
        Tool definition dictionary for Claude Agent SDK
    """
    tool = SentryTracesTool(sentry_client)

    return {
        "name": "query_sentry_traces",
        "description": (
            "Query Sentry API to get trace data and performance metrics for service endpoints. "
            "Use this to analyze actual production behavior, performance characteristics, "
            "and error patterns. Returns transaction traces, performance metrics (p50, p95), "
            "error rates, and recent error events."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "endpoint_path": {
                    "type": "string",
                    "description": (
                        "Specific endpoint to query (e.g., 'POST /api/checkout'). "
                        "Leave empty to query all endpoints."
                    ),
                },
                "stats_period": {
                    "type": "string",
                    "description": "Time period for stats (e.g., '1h', '24h', '7d'). Default: '24h'",
                    "default": "24h",
                },
                "include_errors": {
                    "type": "boolean",
                    "description": "Whether to include error events in the response. Default: true",
                    "default": True,
                },
            },
            "required": [],
        },
        "function": tool,
    }
