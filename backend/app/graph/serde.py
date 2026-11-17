"""Checkpoint serializer that only rebuilds our own known types.

LangGraph checkpoints our dataclasses. Allow-listing them means a tampered checkpoint
cannot make the loader build arbitrary Python objects.
"""

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

ALLOWED: list[tuple[str, str]] = [
    ("app.detectors.types", "Span"),
    ("app.detectors.types", "PiiType"),
    ("app.policy.actions", "Action"),
    ("app.policy.utility", "Decision"),
    ("app.fusion.risk", "RiskReport"),
    ("app.fusion.risk", "RiskLevel"),
    ("app.graph.state", "ReviewItem"),
    ("app.graph.state", "RoundRecord"),
    ("app.graph.state", "Event"),
]


def make_serde() -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=ALLOWED)
