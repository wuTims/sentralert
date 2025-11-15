"""Claude API client for code and metrics analysis."""

import anthropic


class ClaudeClient:
    """Client for interacting with Claude API for analysis tasks."""

    def __init__(self, api_key: str):
        """
        Initialize Claude client.

        Args:
            api_key: Anthropic API key
        """
        self.client = anthropic.Anthropic(api_key=api_key)

    def analyze(self, prompt: str, temperature: float = 0.0) -> str:
        """
        Send analysis request to Claude using Haiku 4.5.

        Args:
            prompt: Analysis prompt to send to Claude
            temperature: Sampling temperature (0.0-1.0)

        Returns:
            Claude's text response

        Raises:
            anthropic.APIError: If the API request fails
        """
        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
