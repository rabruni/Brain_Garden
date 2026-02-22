"""Backward-compatibility shim. Use llm_gateway.py for new code."""
from llm_gateway import *  # noqa: F401,F403
PromptRouter = LLMGateway  # noqa: F405
