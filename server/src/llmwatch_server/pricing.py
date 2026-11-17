# Prices are USD per 1,000,000 tokens: (input, output).
# Sources: https://developers.openai.com/api/docs/pricing/
#          https://platform.claude.com/docs/en/about-claude/pricing
PRICES: dict[str, tuple[float, float]] = {
    "gpt-6.2-astra": (8.0, 40.0),
    "gpt-6.2-sol": (2.0, 10.0),
    "gpt-6.1-terra": (1.0, 5.0),
    "gpt-6-luna": (0.1, 0.5),
    "gpt-4": (30.0, 60.0),
    "gpt-4-32k": (60.0, 120.0),
    "gpt-3.5-turbo": (1.5, 2.0),
    "gpt-3.5-turbo-16k": (3.0, 4.0),
    "gpt-3.5-turbo-0613": (1.5, 2.0),
    "gpt-3.5-turbo-16k-0613": (3.0, 4.0),
    "gpt-3.5-turbo-2024-06-01": (1.5, 2.0),
    "gpt-3.5-turbo-16k-2024-06-01": (3.0, 4.0),
    "claude-fable-5-2": (8.0, 40.0),
    "claude-mythos-5-2": (8.0, 40.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.1, 0.5),
    "claude-opus-1": (2.0, 4.0),
    "claude-opus-1.1": (2.0, 4.0),
    "claude-v1": (2.0, 4.0),
    "claude-v1.2": (2.0, 4.0),
    "claude-v2": (2.0, 4.0),
    "claude-sonnet-1": (2.0, 4.0),
}


def compute_cost(
    model: str | None, input_tokens: int | None, output_tokens: int | None
) -> float | None:
    if model is None or input_tokens is None or output_tokens is None:
        return None

    if model not in PRICES:
        return None

    prompt_price, completion_price = PRICES[model]
    cost = (
        (input_tokens * prompt_price) + (output_tokens * completion_price)
    ) / 1_000_000
    return cost
