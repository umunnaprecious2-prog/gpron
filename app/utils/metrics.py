"""Prometheus metrics for the support agent.

Metrics live in the default prometheus_client registry and are served at
/metrics (see app/routes/metrics.py). Labels are low-cardinality on purpose:
never put conversation ids, emails or message text in a label.
"""

from prometheus_client import Counter, Gauge, Histogram

_LATENCY_BUCKETS = (0.25, 0.5, 1, 2, 3, 5, 8, 12, 20, 30, 60)

support_messages_total = Counter(
    "gpron_support_messages_total", "Customer messages received", ["kind"]
)
support_batch_size = Histogram(
    "gpron_support_batch_size",
    "Customer messages combined into one reply",
    buckets=(1, 2, 3, 4, 5, 7, 10, 15),
)
support_batch_wait_seconds = Histogram(
    "gpron_support_batch_wait_seconds",
    "Time from a batch's first message until generation starts",
    buckets=_LATENCY_BUCKETS,
)
support_replies_total = Counter(
    "gpron_support_replies_total", "Assistant replies delivered", ["outcome"]
)
support_ai_latency_seconds = Histogram(
    "gpron_support_ai_latency_seconds",
    "AI generation latency, including tool rounds",
    buckets=_LATENCY_BUCKETS,
)
support_ai_errors_total = Counter(
    "gpron_support_ai_errors_total", "AI provider failures", ["reason"]
)
support_ai_tokens_total = Counter(
    "gpron_support_ai_tokens_total", "AI tokens used", ["type"]
)
support_generation_retries_total = Counter(
    "gpron_support_generation_retries_total", "Batches re-queued after an AI failure"
)
support_stale_suppressed_total = Counter(
    "gpron_support_stale_suppressed_total",
    "Replies dropped because newer customer messages arrived during generation",
)
support_duplicates_prevented_total = Counter(
    "gpron_support_duplicates_prevented_total",
    "Duplicate messages or replies blocked",
    ["source"],
)
support_transcriptions_total = Counter(
    "gpron_support_transcriptions_total", "Voice note transcriptions", ["outcome"]
)
support_transcription_latency_seconds = Histogram(
    "gpron_support_transcription_latency_seconds",
    "Speech-to-text latency",
    buckets=_LATENCY_BUCKETS,
)
support_tts_total = Counter(
    "gpron_support_tts_total", "Text-to-speech requests", ["outcome"]
)
support_escalations_total = Counter(
    "gpron_support_escalations_total", "Human support requests recorded", ["category"]
)
support_pending_conversations = Gauge(
    "gpron_support_pending_conversations",
    "Conversations due for a reply (queue depth)",
)
