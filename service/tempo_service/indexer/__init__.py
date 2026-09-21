"""Tempo indexer package (AGENTS.md §3.2). Heavy ML imports live inside
stage functions — never at module top level — so the service boots and
serves /health without weights resident (D8: single 8–12GB GPU)."""
