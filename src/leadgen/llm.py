"""Provider abstraction - the ONLY module that knows about model providers.

Selection is env-only (LLM_PROVIDER, LLM_MODEL). Also hosts the mock model
used by tests. Mock + OpenAI land in core-agent, other providers in model-switch.

Skeleton only - implemented in the core-agent / model-switch task.
"""
