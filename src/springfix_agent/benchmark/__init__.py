"""Offline benchmark manifest models and loading helpers.

The benchmark package is deliberately separate from the agent graph.  A
manifest contains gold labels for verification, while the agent only receives
the repository path, issue description, and error log.
"""

from springfix_agent.benchmark.loader import (
    BenchmarkManifestError,
    load_benchmark_cases,
    load_cases,
    load_jsonl,
    load_manifest,
)
from springfix_agent.benchmark.models import (
    BenchmarkCase,
    EvidenceTarget,
    ExpectedMavenResult,
)

__all__ = [
    "BenchmarkCase",
    "BenchmarkManifestError",
    "EvidenceTarget",
    "ExpectedMavenResult",
    "load_benchmark_cases",
    "load_cases",
    "load_jsonl",
    "load_manifest",
]
