"""Verified OpenRouter model ids and prices (USD per million tokens).

Source: https://openrouter.ai/api/v1/models, checked 2026-11-06.
"""

SONNET = "anthropic/claude-sonnet-5.5"
HAIKU = "anthropic/claude-haiku-5.5"

# model id -> (input $/MTok, output $/MTok)
PRICES = {
    SONNET: (2.0, 10.0),
    HAIKU: (0.10, 0.50),
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimated USD cost of a call; raises KeyError for an unpriced model."""
    in_price, out_price = PRICES[model]
    return (prompt_tokens * in_price + completion_tokens * out_price) / 1_000_000
