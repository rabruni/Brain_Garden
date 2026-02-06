"""Brain Module — KERNEL.semantic one-shot reasoning.

Provides a standalone brain_call() that uses a governed prompt (PRM-BRAIN-001)
to analyze system context and produce structured routing/advisory output.

All LLM calls go through stdlib_llm.complete() — no new execution primitives.

Example:
    from modules.brain import brain_call, get_brain_provider_id

    response = brain_call(
        query="what should I do next?",
        system_context={"packages": [...], "health": {...}},
    )
    print(response.intent)             # "general"
    print(response.proposed_next_step)  # "Review installed packages..."
"""

from modules.brain.brain import brain_call, BrainResponse, get_brain_provider_id

__all__ = ["brain_call", "BrainResponse", "get_brain_provider_id"]
