"""HO1 Executor — canonical execution point for all LLM calls.

Every LLM invocation flows through HO1. This enforces:
  - Invariant #1: No direct LLM calls
  - Invariant #3: Agents don't remember, they READ

HO1 receives WorkOrders from HO2, executes them, and returns results.
"""

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path

# Add own kernel to path
sys.path.insert(0, str(Path(__file__).resolve().parent))
# Staging-aware: add PKG-KERNEL-001 for LedgerClient
_staging = Path(__file__).resolve().parents[3]
_kernel_dir = _staging / "PKG-KERNEL-001" / "HOT" / "kernel"
if _kernel_dir.exists():
    sys.path.insert(0, str(_kernel_dir))
    sys.path.insert(0, str(_kernel_dir.parent))

try:
    from ledger_client import LedgerClient, LedgerEntry
except ImportError:
    from kernel.ledger_client import LedgerClient, LedgerEntry


class HO1Executor:
    """HO1 cognitive process — executes work orders via prompt contracts.

    All dependencies are received via DI (dependency injection):
    - gateway: LLM Gateway instance (duck-typed, has .route())
    - ledger: LedgerClient for writing to HO1m
    - budgeter: TokenBudgeter instance (duck-typed, has .check(), .debit())
    - tool_dispatcher: ToolDispatcher instance
    - contract_loader: ContractLoader instance
    - config: dict with agent_id, agent_class, tier, etc.
    """

    def __init__(
        self,
        gateway,
        ledger,
        budgeter,
        tool_dispatcher,
        contract_loader,
        config: dict,
    ):
        self.gateway = gateway
        self.ledger = ledger
        self.budgeter = budgeter
        self.tool_dispatcher = tool_dispatcher
        self.contract_loader = contract_loader
        self.config = config or {}

    def execute(self, work_order: dict) -> dict:
        """Execute a work order and return the completed/failed WO.

        Args:
            work_order: WorkOrder as dict.

        Returns:
            Updated WO dict with output_result, cost, completed_at, state.
        """
        wo = dict(work_order)  # Work on a copy
        start_time = time.time()

        # Initialize cost tracking
        cost = wo.get("cost", {
            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
            "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0,
        })

        try:
            # Step 1: Transition to executing
            self._transition_state(wo, "executing")

            wo_type = wo.get("wo_type", "")
            constraints = wo.get("constraints", {})

            # Step 2: Handle tool_call type specially (no LLM)
            if wo_type == "tool_call":
                result = self._handle_tool_call(wo, cost)
                wo["output_result"] = result
                self._transition_state(wo, "completed")
                cost["elapsed_ms"] = int((time.time() - start_time) * 1000)
                wo["cost"] = cost
                wo["completed_at"] = datetime.now(timezone.utc).isoformat()
                self._log_event("WO_COMPLETED", wo, cost=cost)
                return wo

            # Step 3: Load prompt contract
            contract_id = constraints.get("prompt_contract_id")
            if not contract_id:
                return self._fail_wo(wo, cost, start_time, "contract_not_found", "No prompt_contract_id in constraints")

            try:
                contract = self.contract_loader.load(contract_id)
            except Exception as e:
                return self._fail_wo(wo, cost, start_time, "contract_not_found", str(e))

            # Step 4: Validate input against contract input_schema
            input_context = wo.get("input_context", {})
            input_schema = contract.get("input_schema", {})
            if input_schema:
                valid, errors = self._validate_schema(input_context, input_schema)
                if not valid:
                    return self._fail_wo(wo, cost, start_time, "input_schema_invalid", "; ".join(errors))

            # Step 5: Build PromptRequest
            request = self._build_prompt_request(wo, contract)

            # Step 6: Run tool loop
            turn_limit = constraints.get("turn_limit", 5)
            token_budget = constraints.get("token_budget", 100000)

            # Allocate budget scope before entering the loop
            if self.budgeter:
                from token_budgeter import BudgetAllocation
                scope = self._make_budget_scope(wo, token_budget)
                self.budgeter.allocate(scope, BudgetAllocation(
                    token_limit=token_budget,
                    turn_limit=turn_limit,
                ))

            final_content = None
            for turn in range(turn_limit):
                # Check budget before each call
                if self.budgeter:
                    check = self.budgeter.check(self._make_budget_scope(wo, token_budget - cost.get("total_tokens", 0)))
                    if not check.allowed:
                        return self._fail_wo(wo, cost, start_time, "budget_exhausted", "Token budget exhausted")

                # Call gateway
                try:
                    response = self.gateway.route(request)
                except Exception as e:
                    return self._fail_wo(wo, cost, start_time, "gateway_error", str(e))

                # Update cost
                cost["input_tokens"] += getattr(response, "input_tokens", 0)
                cost["output_tokens"] += getattr(response, "output_tokens", 0)
                cost["total_tokens"] = cost["input_tokens"] + cost["output_tokens"]
                cost["llm_calls"] += 1

                # Log LLM call
                self._log_event("LLM_CALL", wo,
                    input_tokens=getattr(response, "input_tokens", 0),
                    output_tokens=getattr(response, "output_tokens", 0),
                    model_id=getattr(response, "model_id", "unknown"),
                    latency_ms=getattr(response, "latency_ms", 0),
                )

                # Debit budget
                if self.budgeter:
                    self._debit_budget(wo, response)

                content = getattr(response, "content", "")

                # Check for gateway rejection/error
                outcome = getattr(response, "outcome", None)
                if outcome is not None and str(outcome) not in ("SUCCESS", "RouteOutcome.SUCCESS"):
                    error_code = getattr(response, "error_code", "gateway_rejected")
                    error_msg = getattr(response, "error_message", f"Gateway returned {outcome}")
                    return self._fail_wo(wo, cost, start_time, str(error_code), str(error_msg))

                # Check for tool_use blocks
                tool_uses = self._extract_tool_uses(content, response)
                if tool_uses and self.tool_dispatcher:
                    cached_results = []
                    for tu in tool_uses:
                        tool_result = self.tool_dispatcher.execute(tu["tool_id"], tu.get("arguments", {}))
                        cost["tool_calls"] += 1
                        result_output = getattr(tool_result, "output", None)
                        cached_results.append({
                            "tool_id": tu["tool_id"],
                            "result": result_output,
                        })
                        args_str = json.dumps(tu.get("arguments", {}))[:200]
                        result_str = json.dumps(result_output, default=str)[:500] if result_output is not None else ""
                        self._log_event("TOOL_CALL", wo,
                            tool_id=tu["tool_id"],
                            status=getattr(tool_result, "status", "unknown"),
                            args_summary=args_str,
                            result_summary=result_str,
                        )
                    # Build follow-up request with cached tool results
                    tool_results_text = json.dumps(cached_results)
                    request = self._build_prompt_request(wo, contract,
                        additional_context=f"\nTool results: {tool_results_text}")
                    continue
                else:
                    final_content = content
                    break
            else:
                # Turn limit exceeded
                return self._fail_wo(wo, cost, start_time, "turn_limit_exceeded", f"Exceeded turn limit of {turn_limit}")

            # Step 7: Validate output
            output_schema = contract.get("output_schema", {})
            if output_schema and final_content:
                valid, errors = self._validate_output(final_content, output_schema)
                if not valid:
                    return self._fail_wo(wo, cost, start_time, "output_schema_invalid", "; ".join(errors))

            # Step 8: Set output
            try:
                wo["output_result"] = json.loads(final_content) if final_content else {"response_text": ""}
            except (json.JSONDecodeError, TypeError):
                wo["output_result"] = {"response_text": final_content}

            # Step 9: Complete
            self._transition_state(wo, "completed")
            cost["elapsed_ms"] = int((time.time() - start_time) * 1000)
            wo["cost"] = cost
            wo["completed_at"] = datetime.now(timezone.utc).isoformat()
            self._log_event("WO_COMPLETED", wo, cost=cost)
            return wo

        except Exception as e:
            return self._fail_wo(wo, cost, start_time, "execution_error", str(e))

    def _transition_state(self, wo: dict, new_state: str):
        wo["state"] = new_state

    def _fail_wo(self, wo: dict, cost: dict, start_time: float, error_code: str, error_message: str) -> dict:
        self._transition_state(wo, "failed")
        wo["error"] = f"{error_code}: {error_message}"
        cost["elapsed_ms"] = int((time.time() - start_time) * 1000)
        wo["cost"] = cost
        wo["completed_at"] = datetime.now(timezone.utc).isoformat()
        self._log_event("WO_FAILED", wo, error_code=error_code, error_message=error_message)
        return wo

    def _handle_tool_call(self, wo: dict, cost: dict) -> dict:
        constraints = wo.get("constraints", {})
        tools_allowed = constraints.get("tools_allowed", [])
        input_context = wo.get("input_context", {})
        results = {}
        for tool_id in tools_allowed:
            if self.tool_dispatcher:
                result = self.tool_dispatcher.execute(tool_id, input_context)
                cost["tool_calls"] += 1
                results[tool_id] = getattr(result, "output", None)
                self._log_event("TOOL_CALL", wo, tool_id=tool_id, status=getattr(result, "status", "unknown"))
        return results

    def _render_template(self, prompt_pack_id: str, input_ctx: dict, additional_context: str = "") -> str:
        """Load and render a prompt pack template. Falls back to json.dumps if template not found."""
        template_dir = self.contract_loader.contracts_dir.parent / "prompt_packs"
        template_path = template_dir / f"{prompt_pack_id}.txt"
        if not template_path.exists():
            return json.dumps(input_ctx) + additional_context

        template_text = template_path.read_text()
        for key, value in input_ctx.items():
            placeholder = "{{" + key + "}}"
            if isinstance(value, str):
                rendered_value = value
            else:
                rendered_value = json.dumps(value, indent=2)
            template_text = template_text.replace(placeholder, rendered_value)

        return template_text + additional_context

    def _resolve_tools(self, wo: dict) -> Optional[List[dict]]:
        """Resolve tool definitions for the WO based on tools_allowed constraint."""
        tools_allowed = wo.get("constraints", {}).get("tools_allowed", [])
        if not tools_allowed or not self.tool_dispatcher:
            return None
        all_tools = self.tool_dispatcher.get_api_tools()
        allowed_set = set(tools_allowed)
        filtered = [t for t in all_tools if t.get("name") in allowed_set]
        return filtered if filtered else None

    def _build_prompt_request(self, wo: dict, contract: dict, additional_context: str = "") -> object:
        """Build a PromptRequest-compatible object from WO + contract."""
        tools = self._resolve_tools(wo)

        # Import PromptRequest - it's a value object, allowed by FMWK-009
        try:
            from llm_gateway import PromptRequest
        except ImportError:
            # Fallback: create a simple namespace
            from types import SimpleNamespace
            boundary = contract.get("boundary", {})
            input_ctx = wo.get("input_context", {})
            token_budget = wo.get("constraints", {}).get("token_budget", 100000)
            prompt_pack_id = contract.get("prompt_pack_id", "")
            prompt_text = self._render_template(prompt_pack_id, input_ctx, additional_context)
            return SimpleNamespace(
                prompt=prompt_text,
                prompt_pack_id=prompt_pack_id,
                contract_id=contract.get("contract_id", ""),
                agent_id=self.config.get("agent_id", ""),
                agent_class=self.config.get("agent_class", "ADMIN"),
                framework_id=self.config.get("framework_id", "FMWK-000"),
                package_id=self.config.get("package_id", "PKG-HO1-EXECUTOR-001"),
                work_order_id=wo.get("wo_id", ""),
                session_id=wo.get("session_id", ""),
                tier="ho1",
                max_tokens=min(boundary.get("max_tokens", 4096), token_budget),
                temperature=boundary.get("temperature", 0.0),
                tools=tools,
            )

        boundary = contract.get("boundary", {})
        input_ctx = wo.get("input_context", {})
        token_budget = wo.get("constraints", {}).get("token_budget", 100000)
        prompt_pack_id = contract.get("prompt_pack_id", "")
        prompt_text = self._render_template(prompt_pack_id, input_ctx, additional_context)

        return PromptRequest(
            prompt=prompt_text,
            prompt_pack_id=prompt_pack_id,
            contract_id=contract.get("contract_id", ""),
            agent_id=self.config.get("agent_id", ""),
            agent_class=self.config.get("agent_class", "ADMIN"),
            framework_id=self.config.get("framework_id", "FMWK-000"),
            package_id=self.config.get("package_id", "PKG-HO1-EXECUTOR-001"),
            work_order_id=wo.get("wo_id", ""),
            session_id=wo.get("session_id", ""),
            tier="ho1",
            max_tokens=min(boundary.get("max_tokens", 4096), token_budget),
            temperature=boundary.get("temperature", 0.0),
            structured_output=boundary.get("structured_output") if not tools else None,
            input_schema=contract.get("input_schema"),
            output_schema=contract.get("output_schema"),
            template_variables=input_ctx,
            tools=tools,
        )

    def _extract_tool_uses(self, content: str, response: object = None) -> list:
        """Extract tool_use blocks from response content_blocks or content string.

        Prefers content_blocks (populated by AnthropicProvider with full dicts
        including type, id, name, input). Falls back to string parsing for
        non-Anthropic providers.
        """
        # Fast signal: check finish_reason first
        finish_reason = getattr(response, "finish_reason", None) if response else None

        # Primary path: use content_blocks if available
        content_blocks = getattr(response, "content_blocks", None) if response else None
        if content_blocks:
            tool_uses = []
            for block in content_blocks:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_uses.append({
                        "tool_id": block.get("name", ""),
                        "arguments": block.get("input", {}),
                        "id": block.get("id", ""),
                    })
            if tool_uses:
                return tool_uses

        # Fallback: parse content string (for non-Anthropic providers)
        if finish_reason == "tool_use" or content:
            try:
                parsed = json.loads(content)
                if isinstance(parsed, list):
                    return [item for item in parsed if isinstance(item, dict) and item.get("type") == "tool_use"]
                if isinstance(parsed, dict) and parsed.get("type") == "tool_use":
                    return [parsed]
            except (json.JSONDecodeError, TypeError):
                pass
        return []

    def _validate_schema(self, data: dict, schema: dict) -> tuple:
        errors = []
        if schema.get("type") == "object" and "required" in schema:
            for req in schema["required"]:
                if req not in data:
                    errors.append(f"Missing required field: {req}")
        return (len(errors) == 0, errors)

    def _validate_output(self, content: str, schema: dict) -> tuple:
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return (False, [f"Response is not valid JSON: {content[:100]}"])
        return self._validate_schema(parsed, schema)

    def _log_event(self, event_type: str, wo: dict, **metadata):
        entry = LedgerEntry(
            event_type=event_type,
            submission_id=wo.get("wo_id", ""),
            decision=event_type,
            reason=f"{event_type} for {wo.get('wo_id', '')}",
            metadata={
                "provenance": {
                    "agent_id": self.config.get("agent_id", ""),
                    "agent_class": self.config.get("agent_class", "ADMIN"),
                    "work_order_id": wo.get("wo_id", ""),
                    "session_id": wo.get("session_id", ""),
                },
                "scope": {"tier": "ho1"},
                **metadata,
            },
        )
        self.ledger.write(entry)

    def _make_budget_scope(self, wo: dict, remaining: int = 0):
        from token_budgeter import BudgetScope
        return BudgetScope(
            session_id=wo.get("session_id", ""),
            work_order_id=wo.get("wo_id", ""),
            agent_id=self.config.get("agent_id", ""),
            requested_tokens=remaining,
        )

    def _debit_budget(self, wo: dict, response):
        try:
            from token_budgeter import BudgetScope, TokenUsage
            scope = BudgetScope(
                session_id=wo.get("session_id", ""),
                work_order_id=wo.get("wo_id", ""),
                agent_id=self.config.get("agent_id", ""),
            )
            usage = TokenUsage(
                input_tokens=getattr(response, "input_tokens", 0),
                output_tokens=getattr(response, "output_tokens", 0),
                model_id=getattr(response, "model_id", "unknown"),
            )
            self.budgeter.debit(scope, usage)
        except ImportError:
            pass
