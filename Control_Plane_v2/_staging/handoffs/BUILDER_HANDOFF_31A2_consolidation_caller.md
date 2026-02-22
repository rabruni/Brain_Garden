# BUILDER_HANDOFF_31A2: Consolidation Caller in SessionHostV2

## 1. Mission

Complete the H-29 consolidation loop by adding the runtime caller in SessionHostV2. HO2Supervisor's `run_consolidation()` exists and has tests, but nobody calls it at runtime — `process_turn()` in SessionHostV2 drops the `consolidation_candidates` field from the HO2 TurnResult. This handoff adds ~10 lines that read candidates and invoke consolidation. Modifies **PKG-SESSION-HOST-V2-001** only.

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree.
2. **DTT: Design → Test → Then implement.** Write/update tests FIRST.
3. **Package everything.** Use `hashing.py:compute_sha256()` and `packages.py:pack()`. NEVER raw hashlib or shell tar.
4. **End-to-end verification.** Clean-room install → all gates pass.
5. **No file replacement.** In-package modifications to PKG-SESSION-HOST-V2-001 only.
6. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never with `./` prefix.
7. **Results file.** Write `_staging/handoffs/RESULTS_HANDOFF_31A2.md`.
8. **Full regression test.** Run ALL staged package tests. New failures are blockers.
9. **Baseline snapshot.** Input baseline: 22 packages, 693 installed tests, 8/8 gates.
10. **Scope boundary.** PKG-SESSION-HOST-V2-001 ONLY. Do NOT touch PKG-ADMIN-001 or PKG-HO2-SUPERVISOR-001.
11. **Consolidation is out-of-band.** It runs AFTER the response is ready. It does NOT change what the user sees. If it fails, log and continue — never crash the turn.

## 3. Architecture / Design

### Current Flow (broken)

```
SessionHostV2.process_turn(user_message)
  → self._ho2.handle_turn(user_message)
  → result = HO2 TurnResult {
        response, wo_chain_summary, cost_summary,
        session_id, quality_gate_passed,
        consolidation_candidates: ["intent:tool_query"]  ← PRESENT but DROPPED
    }
  → return SHV2 TurnResult(response, outcome, tool_calls, exchange_entry_ids)
     ↑ consolidation_candidates never read, run_consolidation never called
```

### Fixed Flow

```
SessionHostV2.process_turn(user_message)
  → self._ho2.handle_turn(user_message)
  → result = HO2 TurnResult { ... consolidation_candidates: [...] }
  → shv2_result = SHV2 TurnResult(response, outcome, tool_calls, exchange_entry_ids)
  → IF consolidation_candidates is non-empty:
      → try: self._ho2.run_consolidation(candidates)
      → except: log warning, continue (never crash)
  → return shv2_result
```

The key: consolidation runs AFTER the SHV2 TurnResult is constructed but BEFORE it's returned. The response is already determined. Consolidation is a side effect — it writes overlays to HO3 memory for future turns, not the current one.

### Why after result construction, before return?

If consolidation runs before result construction and fails, it could corrupt the result. If it runs after return (impossible in sync code), it can't run at all. So: construct result, attempt consolidation (guarded by try/except), return result regardless.

### Adversarial Analysis: Error Handling

**Hurdles**: `run_consolidation()` dispatches a WO to HO1 → Gateway → Anthropic API. Network failures, budget exhaustion, LLM errors are all possible. If the try/except is too broad, we mask real bugs.

**Not Enough**: Just catching Exception and logging is minimal. We should at least log the signal_ids that failed so the admin can diagnose.

**Too Much**: We could add retry logic, dead-letter queues, or async dispatch. Overkill for MVP. Consolidation will fire again on the next gate crossing.

**Synthesis**: try/except Exception with `logger.warning` that includes the candidate signal_ids. No retry. No crash. The gate will fire again on the next qualifying turn.

## 4. Implementation Steps

### Step 1: Modify process_turn in session_host_v2.py

In `_staging/PKG-SESSION-HOST-V2-001/HOT/kernel/session_host_v2.py`, replace lines 62-69 (the try block inside process_turn):

**Before:**
```python
        try:
            result = self._ho2.handle_turn(user_message)
            return TurnResult(
                response=getattr(result, "response", str(result)),
                outcome="success",
                tool_calls=getattr(result, "tool_calls", []),
                exchange_entry_ids=getattr(result, "exchange_entry_ids", []),
            )
```

**After:**
```python
        try:
            result = self._ho2.handle_turn(user_message)
            turn_result = TurnResult(
                response=getattr(result, "response", str(result)),
                outcome="success",
                tool_calls=getattr(result, "tool_calls", []),
                exchange_entry_ids=getattr(result, "exchange_entry_ids", []),
            )

            # Out-of-band consolidation (H-29 loop completion)
            candidates = getattr(result, "consolidation_candidates", [])
            if candidates:
                try:
                    self._ho2.run_consolidation(candidates)
                except Exception as cons_exc:
                    logger.warning(
                        "Consolidation failed for candidates %s: %s",
                        candidates, cons_exc,
                    )

            return turn_result
```

### Step 2: Write tests (DTT — before implementation)

Add tests to `_staging/PKG-SESSION-HOST-V2-001/HOT/tests/test_session_host_v2.py`.

### Step 3: Governance cycle

1. Update manifest.json SHA256 hashes
2. Delete `.DS_Store`/`__pycache__`, rebuild archive with `pack()`
3. Rebuild `CP_BOOTSTRAP.tar.gz`
4. Clean-room install → all gates pass
5. Full regression → no new failures

## 5. Package Plan

### PKG-SESSION-HOST-V2-001 (modified)

| Field | Value |
|-------|-------|
| Package ID | PKG-SESSION-HOST-V2-001 |
| Layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | hot |

Modified assets:
- `HOT/kernel/session_host_v2.py` — consolidation caller
- `HOT/tests/test_session_host_v2.py` — new tests
- `manifest.json` — hash updates

## 6. Test Plan

### New tests (10)

| Test | Description | Expected |
|------|-------------|----------|
| `test_consolidation_called_when_candidates_present` | HO2 returns candidates → run_consolidation called | run_consolidation called with candidate list |
| `test_consolidation_not_called_when_empty` | HO2 returns empty candidates → not called | run_consolidation not called |
| `test_consolidation_not_called_when_missing` | HO2 result has no consolidation_candidates attr → not called | run_consolidation not called |
| `test_consolidation_failure_does_not_crash_turn` | run_consolidation raises Exception → turn still succeeds | TurnResult returned with outcome="success" |
| `test_consolidation_failure_logged` | run_consolidation raises → warning logged | logger.warning called with candidate info |
| `test_response_unchanged_by_consolidation` | Consolidation runs → response is same as without | response matches HO2 result.response |
| `test_consolidation_runs_after_result_construction` | Verify ordering: result constructed before consolidation | Mock verifies call order |
| `test_consolidation_with_multiple_candidates` | 3 candidates → all passed to run_consolidation | run_consolidation called with all 3 |
| `test_degradation_path_skips_consolidation` | HO2 fails, degrades → no consolidation attempt | run_consolidation not called |
| `test_turn_result_fields_preserved` | All TurnResult fields still populated correctly | response, outcome, tool_calls, exchange_entry_ids all set |

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| session_host_v2.py | `_staging/PKG-SESSION-HOST-V2-001/HOT/kernel/session_host_v2.py` | File to modify |
| HO2 TurnResult | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py:88-96` | consolidation_candidates field |
| run_consolidation | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py:537-603` | Method being called |
| Existing SHV2 tests | `_staging/PKG-SESSION-HOST-V2-001/HOT/tests/test_session_host_v2.py` | Test patterns |
| Kernel hashing | `_staging/PKG-KERNEL-001/HOT/kernel/hashing.py` | compute_sha256() |
| Kernel packages | `_staging/PKG-KERNEL-001/HOT/kernel/packages.py` | pack() |

## 8. End-to-End Verification

```bash
TMPDIR=$(mktemp -d)
cd Control_Plane_v2/_staging
tar xzf CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
cd "$TMPDIR" && bash install.sh --root "$TMPDIR" --dev

PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT:$TMPDIR/HOT/scripts:$TMPDIR/HOT/admin:$TMPDIR/HO1/kernel:$TMPDIR/HO2/kernel" \
  python3 -m pytest "$TMPDIR/HOT/tests" "$TMPDIR/HO1/tests" "$TMPDIR/HO2/tests" -v

python3 "$TMPDIR/HOT/scripts/gate_check.py" --root "$TMPDIR" --all --enforce
```

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `session_host_v2.py` | `_staging/PKG-SESSION-HOST-V2-001/HOT/kernel/` | MODIFY |
| `test_session_host_v2.py` | `_staging/PKG-SESSION-HOST-V2-001/HOT/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-SESSION-HOST-V2-001/` | MODIFY |
| `PKG-SESSION-HOST-V2-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD |
| `RESULTS_HANDOFF_31A2.md` | `_staging/handoffs/` | CREATE |

## 10. Design Principles

1. **Out-of-band.** Consolidation never changes the user-facing response. It's a side effect for future turns.
2. **Fail safe.** If consolidation crashes, the turn succeeds. Log and continue.
3. **Minimal touch.** ~10 lines of new code. No new abstractions.
4. **Order matters.** Construct result first, then attempt consolidation, then return.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project.

**Agent: HANDOFF-31A2** — Add consolidation caller in SessionHostV2 (PKG-SESSION-HOST-V2-001)

Read: `Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_31A2_consolidation_caller.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Write tests FIRST.
3. Use `hashing.py:compute_sha256()` and `packages.py:pack()`. NEVER raw hashlib or shell tar.
4. Hash format: `sha256:<64hex>` (71 chars). Bare hex fails G0A.
5. Clean-room verification: bootstrap extract → install.sh → gates pass.
6. Full regression: ALL staged tests, report total.
7. Results file: `_staging/handoffs/RESULTS_HANDOFF_31A2.md` with all required sections.
8. CP_BOOTSTRAP rebuild with new SHA256.
9. PKG-SESSION-HOST-V2-001 ONLY. Do NOT touch other packages.

**10 Questions:**

1. What SINGLE package does this handoff modify? What method gets the new code?
2. What field on HO2's TurnResult contains the consolidation data? Where is it defined?
3. What method on HO2Supervisor does SessionHostV2 call for consolidation? What does it return?
4. Why does consolidation run AFTER result construction but BEFORE return? What would break if it ran before?
5. What happens if run_consolidation() throws an exception? Show the exact error handling.
6. What does getattr(result, "consolidation_candidates", []) return if the HO2 result has no such attribute?
7. In the degradation path (_degrade method), is consolidation attempted? Why or why not?
8. How many new tests are you adding? Name them.
9. What tar format and hash format do you use?
10. After this handoff, what is the complete path: user message → ... → overlay written to HO3 memory?

**Adversarial:**
11. If consolidation always fails silently, how would an admin know? What logging exists?
12. Could consolidation modify the response variable after it's been set? Why or why not?
13. What happens if candidates=["intent:tool_query"] but HO3Memory is None (H-31A-1 not deployed)?

STOP AFTER ANSWERING. Wait for approval.
```

### Expected Answers

1. PKG-SESSION-HOST-V2-001. The `process_turn()` method in `session_host_v2.py`.
2. `consolidation_candidates: List[str]` on HO2's `TurnResult` dataclass at `ho2_supervisor.py:95`.
3. `run_consolidation(signal_ids: List[str]) -> List[Dict[str, Any]]`. Returns list of completed consolidation WO dicts.
4. If consolidation ran before result construction and failed, it could prevent result construction. By constructing first, the response is guaranteed regardless of consolidation outcome.
5. try/except Exception catches it, `logger.warning("Consolidation failed for candidates %s: %s", candidates, cons_exc)`. Turn result is still returned.
6. Returns `[]` (empty list). The `if candidates:` check is False. No consolidation attempted.
7. No. The degradation path (`_degrade`) bypasses HO2 entirely — it calls Gateway directly. No HO2 TurnResult, no candidates, no consolidation.
8. 10 tests (list all names from test plan).
9. `packages.py:pack()` for archives, `sha256:<64hex>` for hashes.
10. User → Shell → SHV2.process_turn → HO2.handle_turn → post-turn signal logging → gate check → candidates returned → SHV2 reads candidates → SHV2 calls HO2.run_consolidation → HO2 creates consolidation WO → HO1 executes → LLM produces structured artifact → HO3Memory.log_overlay → overlays.jsonl.
11. `logger.warning` logs every failure with the candidate signal_ids and exception. The admin can search logs for "Consolidation failed". Additionally, HO3's signals.jsonl will show signals accumulating without corresponding overlays — a diagnostic signal that consolidation isn't firing.
12. No. `turn_result` is constructed before consolidation runs. The TurnResult is a dataclass instance. `run_consolidation` writes to HO3 memory (overlays.jsonl), not to the turn result object.
13. `run_consolidation` checks `if not self._ho3_memory or not self._config.ho3_enabled: return []`. It returns empty. No overlay written. No error. The candidates were real (HO2 logged signals and gate crossed) but consolidation is a no-op without HO3Memory.
