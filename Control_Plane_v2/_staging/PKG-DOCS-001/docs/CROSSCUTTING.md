# Cross-Cutting Concepts (Reference)
Concise excerpts for concepts explicitly described as cross-cutting across the Control Plane ecosystem.

---

## Attention Envelopes (Control_Plane_v2)
- **Schema description:** “Schema for attention envelopes - cross-cutting concern containers for agent coordination.” (`schemas/attention_envelope.json`)
- **Policy description:** Default attention policy “defines … routing and handling rules for cross-cutting concerns in the control plane chain.” (`scripts/policies/attention_default.yaml`)
- **Role:** Attention envelopes carry escalations/compliance/audit/notifications across planes (HO1–HO3); governed at HO3, consumed by lower tiers; validated via `scripts/validate_attention_policy.py`.

## Memory as Cross-Cutting (AI_ARCH archive)
- Design note: “Memory is really cross-cutting, even if we visualize it as a layer.” (design_log_v1.md)
- Clarification: “memory is cross-cutting and the LLM is a user of the substrate, not the substrate itself.” (design_log_v1.md)
- Implication: Memory services span layers; agents consume shared substrate rather than embedding memory within a single tier.

## Shared Integrity (AI_ARCH capabilities inventory)
- Capability gap: “Shared integrity … Cross-layer integrity … Both layers need integrity. Create shared/ directory for cross-cutting concerns.” (capabilities_inventory.csv)
- Implication: Integrity checks/processes must operate across layers, not per-layer only.

## Cross-Layer Observability & Telemetry (AI_ARCH _locked_system_flattened)
- Principle: “Observability built-in — trace_id enables cross-cutting correlation.” (synaptic_manager/ARCHITECTURE.md)
- Integration goal: “Unified metrics across layers … Trace IDs flow through stack” with “Cross-layer memory queries” in the optimization plan. (the_assist/docs/INTEGRATION_PLAN.md)
- Implication: Trace IDs and telemetry must propagate end-to-end across planes/layers to correlate events and memory accesses.

---

Use this sheet to seed RAG for any cross-cutting governance, memory, or integrity flows. Source files remain the authority for full schemas/policies.
