# Sentralert

An intelligent alert generation system that analyzes your application to propose optimal monitoring alerts using Claude AI.

## Overview

Sentralert combines historical metrics analysis with codebase analysis to automatically suggest Sentry alerts for your Python applications. It uses Claude AI (Haiku 4.5) to intelligently assess which alerts are truly valuable and avoids alert fatigue.

## Architecture

The system is organized into clear components:

```
sentralert/
├── clients/              # External service clients
│   ├── sentry_client.py  # Sentry API client
│   └── claude_client.py  # Claude AI client (uses Haiku 4.5)
├── flows/                # Analysis workflows
│   ├── historical_analysis.py  # Flow 1: Metrics-based alerts
│   └── service_analysis.py     # Flow 2: Codebase-based alerts
├── agent.py              # Main orchestrator
└── cli.py                # Command-line interface
```

## Analysis Modes

### Flow 1: Historical Metrics Analysis

Analyzes Sentry metrics from the past to propose **reactive alerts** based on observed patterns:

- **Latency Regressions**: Detects p95 latency increases > 40% with absolute values > 500ms
- **Error Rate Spikes**: Identifies abnormal error rates (> 50 errors/hour)
- **Failure Rates**: Flags high failure rates per transaction (> 5%)

### Flow 2: Service/Codebase Analysis

Analyzes your Python codebase to propose **proactive alerts** for unmonitored endpoints:

- Scans code to identify all endpoints
- Detects "dormant" endpoints (marked as DORMANT in docstrings)
- Uses Claude AI to assess criticality and suggest appropriate alerts
- Focuses on payment, order, refund, and critical business endpoints

### Agent Mode: Autonomous Service Analysis (NEW)

Uses **Claude Agent SDK** with autonomous tool use to synthesize codebase and production insights:

- **DeepWiki MCP Integration**: Uses the Model Context Protocol (MCP) to query DeepWiki for codebase structure and potential issues
  - Protocol: SSE transport (`https://mcp.deepwiki.com/sse`)
  - Python MCP SDK for standardized AI-data source integration
- **Sentry API Integration**: Analyzes production traces, metrics, and errors
- **Autonomous Analysis**: Agent decides which tools to use and when
- **Structured Output**: JSON-formatted alerts with execution traces
- **Model**: claude-haiku-4-5-20251001

See [agents/README.md](src/sentralert/agents/README.md) for detailed documentation.

## Installation

```bash
# Clone or install the package
pip install -e .

# Or install from PyPI (when published)
pip install sentralert
```

## Usage

### Prerequisites

Set the following environment variables in your `.env` file:

```bash
# Required
ANTHROPIC_API_KEY=your_api_key_here
SENTRY_AUTH_TOKEN=your_token_here
SENTRY_ORG_SLUG=your_org_slug

# Required for Flow 2 (Service Analysis)
TARGET_APP_PATH=/path/to/your/app.py

# Optional (for Agent Mode)
DEEPWIKI_REPO_URL=https://deepwiki.com/wuTims/sentralert-demo-service

# Optional
ALERTS_NOTIFY_EMAIL=your_email@example.com
ENVIRONMENT=production
```

### Running Sentralert

```bash
# Run both flows (traditional)
sentralert

# Or run specific modes
sentralert historical  # Only historical analysis
sentralert service     # Only codebase analysis
sentralert agent       # Autonomous agent mode with deepwiki + Sentry
```

### Agent Mode Details

The agent mode uses the Claude Agent SDK to autonomously:
1. Query deepwiki MCP for codebase insights
2. Query Sentry API for production metrics
3. Synthesize findings to propose intelligent alerts

```bash
# Run agent mode
sentralert agent

# Or use programmatically
python examples/service_analysis_agent_example.py
```

### Output

Sentralert generates YAML files in the `alerts/` directory, one per suggested alert:

```yaml
kind: sentry.metric_alert
flow: historical
name: "Checkout endpoint latency spike"
dataset: transactions
aggregate: p95(transaction.duration)
query: 'event.type:transaction transaction:"GET /checkout" environment:production'
timeWindow: 5
thresholdType: above
environment: production
thresholds:
  warning: 800
  critical: 1200
justification: "Current p95 latency has increased by 60% from baseline..."
severity: HIGH
actions:
  - type: email
    targetType: specific
    targetIdentifier: team@example.com
```

## Demo Features

For demonstration purposes, Flow 2 can intentionally generate one "spammy" alert to demonstrate the value of having AI review the proposed alerts during PR review.

## Key Features

- **Framework Agnostic**: Works with any Python application
- **No emojis**: Clean, professional output
- **Claude Haiku 4.5**: Fast, cost-effective AI analysis
- **Modular design**: Clear separation of concerns
- **YAML output**: Easy to review and version control
- **CI/CD ready**: Designed for PR-based workflows

## Next Steps

After running sentralert:

1. Review generated alerts in `./alerts/`
2. Commit: `git add alerts/ && git commit -m 'Add proposed alerts'`
3. Create PR: `git push && gh pr create`
4. Have your team or AI code reviewer check the PR for alert quality

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests (when available)
pytest

# Format code
ruff format .

# Lint code
ruff check .
```
