# Service Analysis Agent

An intelligent agent built with the Claude Agent SDK that analyzes services by combining codebase insights from deepwiki with production traces from Sentry.

## Overview

The Service Analysis Agent uses **claude-haiku-4-5-20251001** model and operates autonomously to:

1. **Query deepwiki MCP** - Understand codebase structure, endpoints, and potential issues
2. **Query Sentry API** - Analyze actual production metrics, traces, and errors
3. **Synthesize insights** - Combine static code analysis with runtime behavior
4. **Propose alerts** - Generate intelligent monitoring alerts with proper thresholds

## Architecture

```
ServiceAnalysisAgent
├── Tools
│   ├── query_deepwiki_codebase - MCP integration for code insights
│   └── query_sentry_traces - Sentry API for production metrics
├── Agent Loop
│   ├── Autonomous tool selection
│   ├── Atomic execution
│   └── Iterative refinement
└── Output
    ├── Structured JSON alerts
    └── Execution trace
```

### MCP Integration Architecture

The DeepWiki MCP integration is exposed to the Claude Agent SDK as a standard tool:

```
User Request
    ↓
ServiceAnalysisAgent (Claude Agent SDK)
    ↓
query_deepwiki_codebase (Standard Tool Interface)
    ↓
DeepWikiTool.__call__() (Sync Wrapper)
    ↓
DeepWikiTool._query_async() (MCP Client)
    ↓
MCP Protocol (SSE Transport)
    ↓
DeepWiki MCP Server (https://mcp.deepwiki.com/sse)
    ↓
ask_question Tool
    ↓
Response
```

**Key Points:**
- The agent sees `query_deepwiki_codebase` as a regular tool, not knowing about MCP
- MCP protocol handling is encapsulated in `DeepWikiTool`
- Async MCP calls are wrapped in a sync interface for compatibility
- Falls back to mock data if MCP connection fails

## Tools

### 1. `query_deepwiki_codebase`

Queries the deepwiki MCP server for codebase insights using the **Model Context Protocol (MCP)**.

**MCP Integration Details:**
- Protocol: Model Context Protocol (SSE transport)
- Server: `https://mcp.deepwiki.com/sse`
- MCP Tool Used: `ask_question`
- Authentication: None required (free public repositories)

**How It Works:**
1. Establishes SSE connection to DeepWiki MCP server
2. Initializes MCP session
3. Calls the `ask_question` tool with repository and query
4. Returns structured codebase insights

**Input:**
```json
{
  "query": "What API endpoints exist?"
}
```

**Output:**
```json
{
  "query": "What API endpoints exist?",
  "codebase_insights": {
    "endpoints": [
      {
        "path": "/api/checkout",
        "method": "POST",
        "description": "Process customer checkout",
        "monitored": false
      }
    ],
    "services": [...],
    "code_structure": {...},
    "dependencies": [...],
    "potential_issues": [...]
  },
  "metadata": {
    "repo": "wuTims/sentralert-demo-service",
    "source": "deepwiki_mcp"
  }
}
```

**Note:** The tool uses the official Python MCP SDK (`mcp` package) to communicate with the DeepWiki MCP server. If the MCP connection fails, it falls back to mock data for development/testing.

### 2. `query_sentry_traces`

Queries Sentry API for production traces and metrics.

**Input:**
```json
{
  "endpoint_path": "POST /api/checkout",
  "stats_period": "24h",
  "include_errors": true
}
```

**Output:**
```json
{
  "query": {
    "endpoint": "POST /api/checkout",
    "period": "24h"
  },
  "transactions": [
    {
      "name": "POST /api/checkout",
      "metrics": {
        "p50_duration_ms": 245,
        "p95_duration_ms": 890,
        "count": 1523,
        "failure_rate": 0.025
      }
    }
  ],
  "errors": [...],
  "summary": {
    "total_transactions": 1,
    "total_errors": 3,
    "monitored": true
  }
}
```

## Usage

### Basic Usage

```python
from sentralert.agents import ServiceAnalysisAgent
from sentralert.clients import SentryClient

# Initialize clients
sentry_client = SentryClient(
    auth_token="your_token",
    org_slug="your_org"
)

# Create agent
agent = ServiceAnalysisAgent(
    anthropic_api_key="your_api_key",
    sentry_client=sentry_client,
    deepwiki_repo_url="https://deepwiki.com/wuTims/sentralert-demo-service"
)

# Run analysis
suggestions = agent.run_and_format(analysis_type="comprehensive")
```

### Analysis Types

1. **Comprehensive** (default)
   - Full codebase discovery
   - Production metrics analysis
   - Detailed alert proposals

2. **Quick**
   - Focus on critical endpoints only
   - Fast turnaround

3. **Endpoint-specific**
   - Deep dive on a single endpoint
   - Requires `focus_endpoint` parameter

### Advanced Usage

```python
# Get full result with insights and execution trace
result = agent.analyze(analysis_type="comprehensive")

print(result["analysis_summary"])
print(result["insights"])
print(result["suggestions"])
print(result["execution_trace"])
```

## Output Format

### Alert Suggestions

The agent outputs alerts in Sentry metric alert format:

```python
{
    "kind": "sentry.metric_alert",
    "flow": "service_analysis_agent",
    "name": "Checkout failure rate critical",
    "dataset": "transactions",
    "aggregate": "failure_rate()",
    "query": 'event.type:transaction transaction:"POST /api/checkout" environment:production',
    "timeWindow": 5,
    "thresholdType": "above",
    "environment": "production",
    "thresholds": {
        "warning": 1.0,
        "critical": 2.0
    },
    "justification": "Codebase shows external payment API without error handling. Production shows 2.5% failure rate.",
    "severity": "CRITICAL",
    "actions": [...]
}
```

### Execution Trace

Track what the agent did:

```python
{
    "iteration": 1,
    "tool": "query_deepwiki_codebase",
    "input": {"query": "What endpoints exist?"},
    "output": {...}
}
```

## Integration with Existing Flows

You can use the agent alongside existing flows:

```python
from sentralert.agent import AlertAgent
from sentralert.agents import ServiceAnalysisAgent

# Traditional flow-based approach
alert_agent = AlertAgent(sentry_client, claude_client)
traditional_alerts = alert_agent.run(flow="service")

# Agent-based approach
analysis_agent = ServiceAnalysisAgent(api_key, sentry_client)
agent_alerts = analysis_agent.run_and_format()

# Combine results
all_alerts = traditional_alerts + agent_alerts
```

## Environment Variables

```bash
# Required
ANTHROPIC_API_KEY=your_api_key
SENTRY_AUTH_TOKEN=your_sentry_token
SENTRY_ORG_SLUG=your_org

# Optional
ALERTS_NOTIFY_EMAIL=team@example.com
```

## Benefits Over Traditional Flows

1. **Autonomous Decision Making** - Agent decides which tools to use and when
2. **Context Synthesis** - Automatically correlates code + production data
3. **Iterative Refinement** - Can make multiple tool calls to refine analysis
4. **Atomic Execution** - Each tool call is independent and traceable
5. **Structured Output** - Consistent JSON format with execution traces

## Example

See [examples/service_analysis_agent_example.py](../../../examples/service_analysis_agent_example.py) for a complete working example.

## Model

Uses **claude-haiku-4-5-20251001** for:
- Cost-effective analysis
- Fast iteration cycles
- Reliable structured output
- Tool use capabilities
