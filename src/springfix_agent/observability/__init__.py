"""Observability layer: Tracer Protocol and timing types.

M0 defines only the Protocol. ``InMemoryTracer`` implementation lands in M1;
Redis Stream publisher lands in a later milestone.
"""

from springfix_agent.observability.tracer import NodeTiming, Tracer

__all__ = ["Tracer", "NodeTiming"]
