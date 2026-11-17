from llmwatch_server.pricing import compute_cost


def test_compute_cost_for_known_models() -> None:
    assert compute_cost("gpt-6.2-astra", 1_000_000, 0) == 8
    assert compute_cost("gpt-4", 1_000_000, 1_000_000) == 90
    assert compute_cost("claude-opus-5-5", 0, 1_000_000) == 20


def test_compute_cost_for_unknown_model() -> None:
    assert compute_cost("unknown-model", 100_000, 10) is None


def test_compute_cost_with_missing_tokens() -> None:
    assert compute_cost("claude-sonnet-1", None, 100_000) is None
    assert compute_cost("claude-sonnet-1", 100_000, None) is None
