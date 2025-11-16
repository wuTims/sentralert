"""Command-line interface for the Alert Agent."""

import argparse
import json
import os
import subprocess
import sys

from anthropic import Anthropic
from dotenv import load_dotenv

from .agent import AlertAgent
from .agents import ServiceAnalysisAgent
from .clients import ClaudeClient, SentryClient


def generate_branch_name(suggestions: list[dict], anthropic_api_key: str) -> str:
    """
    Use Claude Haiku 3.5 to generate a good git branch name.

    Args:
        suggestions: List of alert suggestions
        anthropic_api_key: Anthropic API key

    Returns:
        Generated branch name
    """
    client = Anthropic(api_key=anthropic_api_key)

    # Summarize the suggestions for the prompt
    summary = "\n".join([f"- {s.get('name', 'Unknown')}" for s in suggestions[:5]])
    if len(suggestions) > 5:
        summary += f"\n- ... and {len(suggestions) - 5} more"

    prompt = f"""Generate a concise git branch name for this set of alert configurations:

{summary}

Requirements:
- Use kebab-case (lowercase with hyphens)
- Start with "alerts/" prefix
- Be descriptive but concise (max 50 chars)
- Include the type of alerts or main focus

Examples:
- alerts/checkout-monitoring
- alerts/payment-failure-detection
- alerts/api-latency-alerts

Respond with ONLY the branch name, nothing else."""

    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}],
    )

    branch_name = response.content[0].text.strip()
    return branch_name


def generate_pr_description(
    suggestions: list[dict], anthropic_api_key: str, flow_type: str = "historical"
) -> str:
    """
    Use Claude to generate a high-quality PR description.

    Args:
        suggestions: List of alert suggestions
        anthropic_api_key: Anthropic API key
        flow_type: Type of analysis flow ("historical" or "service")

    Returns:
        Generated PR description with alert details and CodeRabbit tag
    """
    client = Anthropic(api_key=anthropic_api_key)

    # Build detailed alert summary for Claude
    alert_details = []
    for suggestion in suggestions:
        name = suggestion.get("name", "Unknown")
        justification = suggestion.get("justification", "No justification provided")
        severity = suggestion.get("severity", "MEDIUM")
        aggregate = suggestion.get("aggregate", "")
        query = suggestion.get("query", "")

        # Extract endpoint/transaction from query if available
        endpoint = "N/A"
        if "transaction:" in query:
            # Extract transaction name from query
            import re

            match = re.search(r'transaction:"([^"]+)"', query)
            if match:
                endpoint = match.group(1)

        alert_details.append(
            {
                "name": name,
                "endpoint": endpoint,
                "justification": justification,
                "severity": severity,
                "metric": aggregate,
            }
        )

    # Create detailed JSON for Claude
    alerts_json = json.dumps(alert_details, indent=2)

    prompt = f"""You are creating a pull request description for automated alert configurations generated from Sentry data analysis.

Here are the {len(suggestions)} alerts being proposed:

{alerts_json}

Generate a concise, high-quality PR description with the following structure:

## Alert configurations proposed:

[For each alert, create a bullet point with:
- The alert name
- The endpoint/transaction being monitored (if applicable)
- A brief description of what triggers it]

**Generated from {flow_type} Sentry data analysis.**

@coderabbitai review these alerts for quality and potential false positives

Requirements:
- Be concise but informative
- Focus on WHAT is being monitored, not technical implementation details
- Use clear, professional language
- Include all alerts in a scannable format
- Keep the @coderabbitai tag exactly as shown above

Example format:
## Alert configurations proposed:

- **High error rate in production** - Monitors overall error count; triggers when errors exceed 30/5min
- **/api/checkout high failure rate** - Monitors checkout transaction failures; triggers at >3% failure rate
- **/api/orders slow response time** - Monitors order endpoint latency; triggers when p95 exceeds baseline

**Generated from historical Sentry data analysis.**

@coderabbitai review these alerts for quality and potential false positives"""

    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )

    pr_description = response.content[0].text.strip()
    return pr_description


def auto_git_workflow(
    suggestions: list[dict], alert_files: list, anthropic_api_key: str
) -> None:
    """
    Automatically create branch, commit, and push changes.

    Args:
        suggestions: List of alert suggestions
        alert_files: List of saved alert file paths
        anthropic_api_key: Anthropic API key for branch name generation
    """
    try:
        # Check if git repo exists
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd="/workspaces/python-ai/sentralert",
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print("\n Not a git repository. Initializing git...")
            subprocess.run(["git", "init"], cwd="/workspaces/python-ai/sentralert", check=True)
            print("✓ Git repository initialized")

        # Generate branch name using Claude
        print("\n Generating branch name with Claude Haiku 3.5...")
        branch_name = generate_branch_name(suggestions, anthropic_api_key)
        print(f"✓ Generated branch name: {branch_name}")

        # Create and checkout branch
        print(f"\n Creating branch: {branch_name}")
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd="/workspaces/python-ai/sentralert",
            check=True,
        )

        # Add alert files
        print("\n Adding alert files...")
        subprocess.run(
            ["git", "add", "alerts/"],
            cwd="/workspaces/python-ai/sentralert",
            check=True,
        )

        # Generate commit message with tag for CodeRabbit
        alert_summary = "\n".join([f"  - {s.get('name', 'Unknown')}" for s in suggestions])
        commit_message = f"""Add {len(suggestions)} alert configuration(s)

Alert configurations proposed:
{alert_summary}

@coderabbitai review
"""

        # Commit changes
        print("\n Creating commit...")
        subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd="/workspaces/python-ai/sentralert",
            check=True,
        )
        print("✓ Commit created")

        # Push branch
        print(f"\n Pushing branch: {branch_name}")
        subprocess.run(
            ["git", "push", "-u", "origin", branch_name],
            cwd="/workspaces/python-ai/sentralert",
            check=True,
        )
        print("✓ Branch pushed successfully")

        # Detect flow type from suggestions
        flow_type = "historical"
        if suggestions and suggestions[0].get("flow") == "service_analysis_agent":
            flow_type = "service"

        # Generate PR description using Claude
        print("\n Generating PR description with Claude...")
        pr_description = generate_pr_description(
            suggestions, anthropic_api_key, flow_type
        )
        print("✓ PR description generated")

        # Display PR details for manual creation
        print("\n" + "=" * 70)
        print("PR TITLE:")
        print(f"Add {len(suggestions)} alert configuration(s)")
        print("\nPR DESCRIPTION:")
        print(pr_description)
        print("=" * 70)

        print("\n Auto workflow complete!")
        print("\nNext steps:")
        print(f"  1. Go to GitHub and create a PR from branch '{branch_name}' to 'main'")
        print("  2. Copy the PR description above")
        print("  3. CodeRabbit will automatically review the PR")

    except subprocess.CalledProcessError as e:
        print(f"\n Git operation failed: {e}")
        print("You may need to manually commit and push the changes.")
    except Exception as e:
        print(f"\n Auto workflow failed: {e}")
        print("You may need to manually commit and push the changes.")


def main():
    """Main CLI entry point for running the Alert Agent."""
    # Load environment variables from .env file
    load_dotenv()

    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Intelligent alert generation system for monitoring platforms",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sentralert historical          # Analyze historical Sentry data
  sentralert service             # Analyze service codebase for unmonitored endpoints
  sentralert service --auto      # Analyze and auto-commit to git branch
        """,
    )

    parser.add_argument(
        "mode",
        choices=["historical", "service"],
        help="Analysis mode: 'historical' for past metrics, 'service' for codebase analysis",
    )

    parser.add_argument(
        "--auto",
        action="store_true",
        help="Automatically create git branch, commit, and push changes",
    )

    args = parser.parse_args()

    # Validate required environment variables
    required_vars = ["SENTRY_AUTH_TOKEN", "SENTRY_ORG_SLUG", "ANTHROPIC_API_KEY"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        print("Error: Missing required environment variables:")
        for var in missing_vars:
            print(f"  - {var}")
        print("\nPlease set these variables in your .env file or environment.")
        sys.exit(1)

    # Initialize clients
    sentry = SentryClient(
        auth_token=os.environ["SENTRY_AUTH_TOKEN"],
        org_slug=os.environ["SENTRY_ORG_SLUG"],
    )

    claude = ClaudeClient(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Initialize agent
    agent = AlertAgent(sentry, claude)

    # Run analysis based on mode
    if args.mode == "service":
        print("\n Running Service Analysis Agent (Claude Agent SDK)...")
        analysis_agent = ServiceAnalysisAgent(
            anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
            sentry_client=sentry,
            deepwiki_repo_url=os.getenv(
                "DEEPWIKI_REPO_URL", "https://deepwiki.com/wuTims/sentralert-demo-service"
            ),
        )
        suggestions = analysis_agent.run_and_format(analysis_type="comprehensive")
    else:  # historical
        print(f"\n Running Historical Analysis...")
        suggestions = agent.run(flow="historical")

    # Save results
    if suggestions:
        print("\n Saving suggestions as YAML files...")
        files = agent.save_as_yaml(suggestions)
        print(f"\n✓ Saved {len(files)} alert file(s) to ./alerts/")

        # Auto workflow if requested
        if args.auto:
            auto_git_workflow(suggestions, files, os.environ["ANTHROPIC_API_KEY"])
        else:
            print("\nNext steps:")
            print("  1. Review the alerts in ./alerts/")
            print("  2. Run with --auto flag to automatically create branch and push")
            print("     OR")
            print("  3. Manually commit: git add alerts/ && git commit")
            print("  4. Create PR: gh pr create")
    else:
        print("\n  No alerts suggested")


if __name__ == "__main__":
    main()
