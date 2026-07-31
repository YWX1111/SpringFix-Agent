"""M3 retrieval module: multi-channel code retrieval with BM25 + baseline + symbol.

Architecture:

    QueryBuilder → RetrievalQuery
    Chunker → list[CodeChunk]
    Index → {Baseline, BM25, Symbol}
    Fusion (RRF) → list[RetrievalHit]
    Diagnostics → timing and scale metadata

This module does NOT call any LLM and does NOT modify the 7-node graph.
"""
