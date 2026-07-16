"""LangGraph state and workflow definitions.

M1 implements a 4-node static linear graph:
    START -> validate_input -> explore_repository -> retrieve_code -> build_basic_report -> END
"""

from springfix_agent.graph.builder import build_graph

__all__ = ["build_graph"]
