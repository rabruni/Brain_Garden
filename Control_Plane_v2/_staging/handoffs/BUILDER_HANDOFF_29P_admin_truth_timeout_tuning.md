# BUILDER_HANDOFF_29P: Admin Reliability Patch — Timeout Resilience + Grounded Responses + Tuning Accessibility

## 1. Mission

Patch the ADMIN runtime so it:
1. Stops failing on long requests with single-shot timeout behavior.
2. Stops making ungrounded claims about ledgers/files/tools when evidence was not retrieved.
3. Makes tuning and runtime controls easy to discover from ADMIN tools.

This is a targeted reliability patch. No architecture rewrite.

## 2. Grounding (Required Docs)

- `Control_Plane_v2/_staging/architecture/KERNEL_PHASE_2_v2.md`
  - Invariant #1: all LLM calls flow through the LLM Gateway.
  - Invariant #3: agents do not remember internally; they READ from ledgers/context.
  - Invariant #5: budgets are enforced.
- `Control_Plane_v2/_staging/architecture/DESIGN_PHILOSOPHY.md`
  - KERNEL.syntactic remains deterministic.
  - E2E smoke is mandatory for dispatch-path changes.

## 3. User-Visible Failures to Fix

1. `ProviderError(TIMEOUT)` on verbose admin requests.
2. Assistant claims source visibility ("I can see in ledger/code/files") without turn evidence.
3. Tuning/runtime settings are not easy to inspect from ADMIN.

## 4. Scope (Targeted)

### Fix A — Timeout Resilience in Gateway
Package: `PKG-LLM-GATEWAY-001`

- Make router timeout configurable from ADMIN config wiring.
- Implement bounded retry policy for retryable provider failures only:
  - `TIMEOUT`, `RATE_LIMITED`, `SERVER_ERROR`, connection timeout class.
- Keep retries bounded (max attempts + bounded backoff).
- Preserve existing exchange/reject logging; add retry metadata in error/exchange records.

### Fix B — Grounded Response Guardrail
Packages: `PKG-HO1-EXECUTOR-001`, `PKG-HO2-SUPERVISOR-001`

- Update synthesize prompt instructions to forbid ungrounded source claims.
- If evidence is missing, response must explicitly say evidence is not available and suggest relevant tool call.
- Add quality-gate check for ungrounded source-visibility claims:
  - If source-visibility claim exists without evidence from current turn artifacts (`prior_results`, tool outputs, assembled context), reject with retry reason `ungrounded_source_claim`.

### Fix C — Admin Tuning Visibility Tools
Package: `PKG-ADMIN-001`

Add two read-only tools:
1. `show_runtime_config`
   - Returns effective runtime values: provider/model, timeout, retries, budget mode, key budget fields, tool profile, enabled tool ids.
2. `list_tuning_files`
   - Returns canonical tunable file paths: admin config, relevant contracts, prompt packs, gateway-related config sources.

Both must be included in `admin_config.json` `tools[]` so HO2 exposes them.

### Fix D — Config Wiring
Package: `PKG-ADMIN-001`

Add config fields:
- `llm_timeout_ms`
- `llm_max_retries`
- `llm_retry_backoff_ms`

Wire these into `RouterConfig(...)` at gateway construction.

## 5. Files Summary (Only These)

1. `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py`
2. `_staging/PKG-LLM-GATEWAY-001/HOT/tests/test_llm_gateway.py`
3. `_staging/PKG-HO1-EXECUTOR-001/HO1/prompt_packs/PRM-SYNTHESIZE-001.txt`
4. `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/quality_gate.py`
5. `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/test_quality_gate.py`
6. `_staging/PKG-ADMIN-001/HOT/admin/main.py`
7. `_staging/PKG-ADMIN-001/HOT/config/admin_config.json`
8. `_staging/PKG-ADMIN-001/HOT/tests/test_admin.py`
9. `_staging/handoffs/RESULTS_HANDOFF_29P.md` (create at end)

Do not modify files outside this list.

## 6. Test Plan (DTT)

### Gateway
- `test_route_retries_on_timeout_then_success`
- `test_route_stops_after_max_retries_on_timeout`
- `test_route_does_not_retry_non_retryable_auth_error`
- `test_route_uses_configured_timeout_ms`

### Grounding
- `test_quality_gate_rejects_ungrounded_source_claim`
- `test_quality_gate_accepts_source_claim_when_tool_evidence_present`
- `test_synthesize_prompt_contains_grounding_rules`

### Admin
- `test_show_runtime_config_tool_returns_effective_values`
- `test_list_tuning_files_tool_returns_expected_paths`
- `test_tools_present_in_admin_config_and_tools_allowed`
- `test_router_config_wired_from_admin_config`

## 7. E2E Verification (Real Admin Shell)

1. Long verbose request that previously timed out.
   - Expect success or bounded retries with explicit retry trail (no silent drop).
2. Ask code/ledger question without prior tool evidence.
   - Expect explicit "no evidence available yet" + tool proposal; no fabricated source claim.
3. Invoke tuning tools via normal tool loop.
   - `show_runtime_config` returns effective runtime settings.
   - `list_tuning_files` returns canonical tunable paths.

## 8. Governance Cycle

1. Update all affected `manifest.json` hashes with `sha256:<64hex>` format.
2. Repack changed package archives via `packages.py:pack()`.
3. Rebuild `CP_BOOTSTRAP.tar.gz`.
4. Clean-room install and run full regression.
5. Run all governance gates.
6. Write `_staging/handoffs/RESULTS_HANDOFF_29P.md` using full standard template.

## 9. Agent Prompt (10Q Gate)

You are a builder agent for Control Plane v2.

**Agent: HANDOFF-29P** — Admin reliability patch (timeout + grounded responses + tuning access)

Read:
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_29P_admin_truth_timeout_tuning.md`

Before writing ANY code, answer these 10 questions, then STOP and WAIT for approval:

1. What are the three user-visible failures this patch fixes?
2. Where is gateway timeout currently sourced, and why do TIMEOUT failures terminate too aggressively today?
3. Which provider error codes are retryable in this handoff, and which are explicitly non-retryable?
4. What does "ungrounded source claim" mean in this patch, and what evidence is required to allow source-visibility claims?
5. Why does this patch align with v2 Invariants #1, #3, and #5?
6. What two new admin tools are added, and what exact data does each return?
7. Which config fields are added for timeout/retry tuning, and where are they wired into runtime?
8. How many tests are added per package (Gateway, HO2/quality gate, ADMIN)? List test names.
9. Which `manifest.json` files and package archives must be updated/rebuilt?
10. What exact E2E admin-shell sequence proves all three failures are fixed?

**STOP AFTER ANSWERING.** Do NOT proceed until explicit approval.

## 10. Adversarial Bonus (Mandatory)

11.1 **Failure Mode:** If this fails at Gate G3 (Package Integrity), which file/hash in scope is most likely culprit?
11.2 **Shortcut Check:** Which kernel tools are mandatory for hashing/packing, and why must shell shortcuts be avoided?
11.3 **Semantic Audit:** Define one ambiguous term in this handoff precisely so implementation cannot drift.
