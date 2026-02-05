"""Agent runner with capability enforcement and sandbox isolation.

Executes agent turns with full governance enforcement including capability
checking, sandbox isolation, and dual ledger writing.

Example:
    from modules.agent_runtime import AgentRunner, TurnRequest, TurnResult

    runner = AgentRunner("PKG-ADMIN-001", tier="ho1")

    def handler(request: TurnRequest) -> TurnResult:
        return TurnResult(status="ok", result={"answer": "42"}, evidence={})

    request = TurnRequest(
        session_id="SES-abc123",
        turn_number=1,
        query={"question": "What is the meaning of life?"},
        declared_inputs=[],
        declared_outputs=[]
    )

    result = runner.execute_turn(request, handler)
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from modules.agent_runtime.capability import CapabilityEnforcer
from modules.agent_runtime.exceptions import CapabilityViolation, PackageNotFoundError
from modules.agent_runtime.ledger_writer import LedgerWriter
from modules.agent_runtime.sandbox import TurnSandbox
from modules.agent_runtime.session import Session


@dataclass
class DeclaredInput:
    """A declared input file."""
    path: str
    hash: str
    role: str = "input"


@dataclass
class DeclaredOutput:
    """A declared output file."""
    path: str
    role: str = "output"


@dataclass
class TurnRequest:
    """Request for a single agent turn."""
    session_id: str
    turn_number: int
    query: Any
    declared_inputs: List[Dict[str, Any]]
    declared_outputs: List[Dict[str, Any]]
    work_order_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


@dataclass
class TurnResult:
    """Result of a single agent turn."""
    status: str  # "ok" | "error"
    result: Any
    evidence: Dict[str, Any]
    error: Optional[Dict[str, Any]] = None


def hash_json(obj: Any) -> str:
    """Compute SHA256 hash of JSON-serializable object."""
    import hashlib
    json_str = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    h = hashlib.sha256(json_str.encode("utf-8")).hexdigest()
    return f"sha256:{h}"


class AgentRunner:
    """Execute agent turns with capability enforcement."""

    def __init__(
        self,
        package_id: str,
        tier: str = "ho1",
        root: Optional[Path] = None,
    ):
        """Load agent package and capabilities.

        Args:
            package_id: Package identifier (e.g., "PKG-ADMIN-001")
            tier: Execution tier (ho1, ho2, ho3)
            root: Optional root directory

        Raises:
            PackageNotFoundError: If package not found
        """
        self.package_id = package_id
        self.tier = tier
        self.root = root or self._get_default_root()

        # Load package and capabilities
        self.manifest = self._load_package(package_id)
        self.capabilities = self.manifest.get("capabilities", {
            "read": [],
            "write": [],
            "execute": [],
            "forbidden": [],
        })
        self.enforcer = CapabilityEnforcer(self.capabilities)

    def _get_default_root(self) -> Path:
        """Get default Control Plane root."""
        current = Path(__file__).resolve()
        while current.name != "Control_Plane_v2" and current.parent != current:
            current = current.parent
        if current.name == "Control_Plane_v2":
            return current
        return Path.cwd()

    def _load_package(self, package_id: str) -> Dict:
        """Load package manifest from installed directory.

        Args:
            package_id: Package identifier

        Returns:
            Package manifest dictionary

        Raises:
            PackageNotFoundError: If package not found
        """
        manifest_path = self.root / "installed" / package_id / "manifest.json"

        if not manifest_path.exists():
            raise PackageNotFoundError(
                package_id,
                searched_paths=[str(manifest_path)],
            )

        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _validate_request(self, request: TurnRequest) -> None:
        """Validate turn request.

        Args:
            request: Turn request to validate

        Raises:
            ValueError: If request is invalid
            CapabilityViolation: If declared outputs exceed capabilities
        """
        if request.declared_outputs is None:
            raise ValueError(
                "declared_outputs is required (use empty list for read-only turns)"
            )

        # Check that all declared outputs match write capabilities
        self.enforcer.check_declared_outputs(request.declared_outputs)

    def execute_turn(
        self,
        request: TurnRequest,
        handler: Callable[[TurnRequest], TurnResult],
    ) -> TurnResult:
        """Execute a single turn with full governance enforcement.

        Args:
            request: Turn request with query and declarations
            handler: Function that processes the request

        Returns:
            TurnResult with status, result, and evidence
        """
        # 1. Validate request
        try:
            self._validate_request(request)
        except (ValueError, CapabilityViolation) as e:
            return TurnResult(
                status="error",
                result=None,
                evidence={
                    "session_id": request.session_id,
                    "turn_number": request.turn_number,
                    "error_type": type(e).__name__,
                },
                error={"code": type(e).__name__, "message": str(e)},
            )

        # 2. Create/use session
        session = Session(
            tier=self.tier,
            session_id=request.session_id,
            work_order_id=request.work_order_id,
            root=self.root,
        )
        session.start()

        # 3. Initialize ledger writer
        writer = LedgerWriter(session)

        # 4. Execute in sandbox
        sandbox = TurnSandbox(
            request.session_id,
            request.declared_outputs,
            root=self.root,
        )

        try:
            with sandbox:
                # Execute handler
                result = handler(request)

            # 5. Verify writes
            realized_writes, valid = sandbox.verify_writes()

            if not valid:
                # Write violation evidence
                violation = {
                    "undeclared_writes": list(
                        set(r["path"] for r in realized_writes) -
                        set(d["path"] for d in request.declared_outputs)
                    ),
                    "missing_writes": list(
                        set(d["path"] for d in request.declared_outputs) -
                        set(r["path"] for r in realized_writes)
                    ),
                }
                writer.write_violation(
                    turn_number=request.turn_number,
                    violation=violation,
                    work_order_id=request.work_order_id,
                )
                return TurnResult(
                    status="error",
                    result=None,
                    evidence={
                        "session_id": request.session_id,
                        "turn_number": request.turn_number,
                        "violation": violation,
                    },
                    error={
                        "code": "WRITE_SURFACE_MISMATCH",
                        "message": "Realized writes don't match declared outputs",
                        "details": violation,
                    },
                )

            # 6. Compute evidence hashes
            query_hash = hash_json(request.query)
            result_hash = hash_json(result.result)

            # 7. Write to both ledgers
            writer.write_turn(
                turn_number=request.turn_number,
                exec_entry={
                    "query_hash": query_hash,
                    "result_hash": result_hash,
                    "status": result.status,
                },
                evidence_entry={
                    "declared_reads": request.declared_inputs,
                    "declared_writes": realized_writes,
                    "external_calls": result.evidence.get("external_calls", []),
                },
                work_order_id=request.work_order_id,
            )

            # 8. Enrich result evidence
            result.evidence.update({
                "session_id": request.session_id,
                "turn_number": request.turn_number,
                "query_hash": query_hash,
                "result_hash": result_hash,
            })
            if request.work_order_id:
                result.evidence["work_order_id"] = request.work_order_id

            return result

        except CapabilityViolation as e:
            writer.write_violation(
                turn_number=request.turn_number,
                violation=e.to_dict(),
                work_order_id=request.work_order_id,
            )
            return TurnResult(
                status="error",
                result=None,
                evidence={
                    "session_id": request.session_id,
                    "turn_number": request.turn_number,
                    "violation": e.to_dict(),
                },
                error={"code": "CAPABILITY_VIOLATION", "message": str(e)},
            )

        except Exception as e:
            # Log unexpected errors
            return TurnResult(
                status="error",
                result=None,
                evidence={
                    "session_id": request.session_id,
                    "turn_number": request.turn_number,
                    "error_type": type(e).__name__,
                },
                error={"code": "UNEXPECTED_ERROR", "message": str(e)},
            )

        finally:
            session.end()
