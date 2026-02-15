# Reading Order

**Updated**: 2026-02-12

This file is the entry point for any session (human or agent). Read in order.

---

## 1. Current State (start here)

| # | File | Date | Status | What it is |
|---|------|------|--------|-----------|
| 1 | `architecture/SEMANTIC_ARCHITECTURE_PLAN.md` | Feb 12 | CURRENT | The implementation plan: 4 frameworks + 5 packages for cognitive dispatch |
| 2 | `FMWK-008_Work_Order_Protocol/work_order_protocol.md` | Feb 12 | DRAFT | First governance framework: work order as atomic unit of dispatch |

## 2. Reference (foundational, evolved from)

| # | File | Date | Status | What it is |
|---|------|------|--------|-----------|
| 3 | `architecture/KERNEL_PHASE_2.md` | Feb 10 | REFERENCE | Theory: biological stack, agent classes, attention deep dive, learning loops. Superseded by semantic plan where they diverge. |
| 4 | `architecture/ADMIN_DESIGN.md` | Feb 11, updated Feb 12 | CURRENT | ADMIN agent design: cognitive dispatch, component registry, design questions |

## 3. Agent Dispatch

| # | File | Status | What it is |
|---|------|--------|-----------|
| 5 | `handoffs/BUILDER_HANDOFF_STANDARD.md` | CURRENT | The template: 10-question gate, DTT, results format |

## 4. Handoff Registry

| ID | Package | Status | Spec | Agent Prompt | Results |
|----|---------|--------|------|-------------|---------|
| HANDOFF-2 | Install lifecycle | VALIDATED | `handoffs/BUILDER_HANDOFF_2_install_lifecycle.md` | — | — |
| HANDOFF-3 | Prompt Router + Token Budgeter | VALIDATED | `handoffs/BUILDER_HANDOFF_3_prompt_router.md` | — | — |
| FOLLOWUP-3A | Governance health | VALIDATED | `handoffs/BUILDER_FOLLOWUP_3A_governance_health.md` | — | — |
| FOLLOWUP-3B | Bootstrap installer | VALIDATED | `handoffs/BUILDER_FOLLOWUP_3B_bootstrap_installer.md` | — | — |
| FOLLOWUP-3C | Layout 002 | VALIDATED | `handoffs/BUILDER_FOLLOWUP_3C_layout_002.md` | — | `handoffs/RESULTS_FOLLOWUP_3C.md` |
| FOLLOWUP-3D | Genesis G0K fix | VALIDATED | `handoffs/BUILDER_FOLLOWUP_3D_genesis_g0k_fix.md` | — | `handoffs/RESULTS_FOLLOWUP_3D.md` |
| FOLLOWUP-3E | Path authority | VALIDATED | `handoffs/BUILDER_FOLLOWUP_3E_path_authority.md` | — | `handoffs/RESULTS_FOLLOWUP_3E.md` |
| HANDOFF-4 | Attention Service | IN BOOTSTRAP | `handoffs/BUILDER_HANDOFF_4_attention_service.md` | — | — |
| HANDOFF-5 | Flow Runner | SUPERSEDED (absorbed by HO2+HO1) | `handoffs/BUILDER_HANDOFF_5_flow_runner.md` | — | — |
| HANDOFF-6 | Ledger Query | NOT DISPATCHED | `handoffs/BUILDER_HANDOFF_6_ledger_query.md` | — | — |
| HANDOFF-7 | Signal Detector | NOT DISPATCHED | `handoffs/BUILDER_HANDOFF_7_signal_detector.md` | — | — |
| HANDOFF-8 | Learning Loops | NOT DISPATCHED | `handoffs/BUILDER_HANDOFF_8_learning_loops.md` | — | — |
| HANDOFF-9 | Anthropic Provider | VALIDATED | `handoffs/BUILDER_HANDOFF_9_anthropic_provider.md` | — | `handoffs/RESULTS_HANDOFF_9.md` |
| FOLLOWUP-9A | Provider SDK rewrite | VALIDATED | `handoffs/BUILDER_FOLLOWUP_9A_sdk_provider.md` | — | `handoffs/RESULTS_FOLLOWUP_9A.md` |
| HANDOFF-10 | Prompt Router (exchange) | VALIDATED | `handoffs/BUILDER_HANDOFF_10_exchange_recording.md` | — | `handoffs/RESULTS_HANDOFF_10.md` |
| HANDOFF-11 | Session Host + ADMIN | VALIDATED | `handoffs/BUILDER_HANDOFF_11_session_host.md` | — | `handoffs/RESULTS_HANDOFF_11.md` |
| HANDOFF-12 | Boot Materialize | VALIDATED | `handoffs/BUILDER_HANDOFF_12_boot_materialize.md` | `handoffs/AGENT_PROMPT_HANDOFF_12.md` | `handoffs/RESULTS_HANDOFF_12.md` |
| HANDOFF-12A | Pristine fix | VALIDATED | `handoffs/BUILDER_HANDOFF_12A_pristine_fix.md` | `handoffs/AGENT_PROMPT_HANDOFF_12A.md` | `handoffs/RESULTS_HANDOFF_12A.md` |
| CLEANUP-0 | Cleanup | DONE | — | — | `handoffs/RESULTS_CLEANUP_0.md` |
| CLEANUP-1 | Flow Runner removal | VALIDATED | `handoffs/BUILDER_CLEANUP_1_flow_runner.md` | `handoffs/AGENT_PROMPT_CLEANUP_1.md` | `handoffs/RESULTS_CLEANUP_1.md` |

## 5. Directory Layout

```
_staging/
├── READING_ORDER.md              ← you are here
├── architecture/                 ← PROCESS: design docs (read first)
├── handoffs/                     ← PROCESS: agent dispatch specs + results
├── FMWK-008_Work_Order_Protocol/ ← PRODUCT: framework draft
├── PKG-*/                        ← PRODUCT: package source + archives
├── CP_BOOTSTRAP.tar.gz           ← PRODUCT: distribution archive
├── README.md, INSTALL.md         ← PRODUCT: distribution docs
└── install.sh, resolve_install_order.py  ← PRODUCT: install scripts
```

**PROCESS** docs (architecture/, handoffs/) are how we design and build.
**PRODUCT** files (everything else) are destined for the system. They have real path references. Don't move them.

## 6. Critical Path

```
DONE:  Full bootstrap → ADMIN first boot (16 packages, 8/8 gates)
DONE:  HANDOFF-12A → pristine bypass fix
DONE:  CLEANUP-1 → PKG-FLOW-RUNNER-001 removed
NOW:   Ledger metadata schema design (BLOCKING — must resolve before HANDOFF-13)
       FMWK-008 Section 5 needs metadata key standard for relational/graph fields
NEXT:  FMWK-009, 010, 011 → then HANDOFF-13 (PKG-WORK-ORDER-001)
       → HANDOFF-14/15 parallel (HO1 Executor + HO2 Supervisor)
       → HANDOFF-16 (Session Host rewire)
       → HANDOFF-17 (Shell UX — lower priority)
```
