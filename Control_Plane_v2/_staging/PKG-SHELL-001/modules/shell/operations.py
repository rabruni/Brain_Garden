"""Shell operations for pipe-first interface.

Each handler receives a request dict and returns a response envelope
per FMWK-100 §7 pipe-first contract.

Response envelope format:
{
    "status": "ok" | "error",
    "result": { ... },  // operation-specific result
    "error": { "code": "...", "message": "...", "details": {...} },  // only on error
    "evidence": {
        "timestamp": "ISO8601",
        "input_hash": "sha256:...",
        "output_hash": "sha256:...",
        "declared_reads": [...],
        "declared_writes": [...]
    }
}
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Root path for Control Plane
ROOT = Path(__file__).parent.parent.parent


def _get_timestamp() -> str:
    """Get current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _hash_json(obj: Dict[str, Any]) -> str:
    """Compute SHA256 hash of JSON object."""
    try:
        from modules.stdlib_evidence import hash_json
        return hash_json(obj)
    except ImportError:
        # Fallback if stdlib_evidence not available
        import hashlib
        json_str = json.dumps(obj, sort_keys=True, ensure_ascii=False)
        h = hashlib.sha256(json_str.encode("utf-8")).hexdigest()
        return f"sha256:{h}"


def _get_inspector():
    """Get CPInspector instance."""
    try:
        from lib.agent_helpers import CPInspector
        return CPInspector(ROOT)
    except ImportError:
        return None


def _make_response(
    status: str,
    result: Any = None,
    error: Optional[Dict[str, Any]] = None,
    evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build standard response envelope."""
    response = {"status": status}
    if result is not None:
        response["result"] = result
    if error is not None:
        response["error"] = error
    if evidence is not None:
        response["evidence"] = evidence
    return response


def _make_error(code: str, message: str, details: Any = None) -> Dict[str, Any]:
    """Build error object."""
    error = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return error


def handle_pkg_list(request: Dict[str, Any]) -> Dict[str, Any]:
    """List installed packages.

    Request:
        {"operation": "pkg_list"}
        Optional: {"operation": "pkg_list", "plane": "ho3"}

    Response:
        {
            "status": "ok",
            "result": {
                "packages": [
                    {"package_id": "...", "version": "...", "assets_count": N, "package_type": "..."}
                ]
            },
            "evidence": {...}
        }
    """
    inspector = _get_inspector()
    if not inspector:
        return _make_response(
            "error",
            error=_make_error("INSPECTOR_UNAVAILABLE", "CPInspector not available"),
        )

    plane = request.get("plane", "ho3")
    packages, evidence = inspector.list_installed(plane=plane)

    return _make_response(
        "ok",
        result={
            "packages": [
                {
                    "package_id": p.package_id,
                    "version": p.version,
                    "assets_count": p.assets_count,
                    "package_type": p.package_type,
                    "plane_id": p.plane_id,
                    "installed_at": p.installed_at,
                }
                for p in packages
            ],
            "count": len(packages),
        },
        evidence={
            "timestamp": _get_timestamp(),
            "input_hash": _hash_json(request),
            "declared_reads": [{"path": evidence.path, "hash": evidence.hash}],
        },
    )


def handle_pkg_info(request: Dict[str, Any]) -> Dict[str, Any]:
    """Get package details.

    Request:
        {"operation": "pkg_info", "package_id": "PKG-TEST-001"}

    Response:
        {
            "status": "ok",
            "result": {
                "package_id": "...",
                "version": "...",
                "spec_id": "...",
                "assets": [...]
            },
            "evidence": {...}
        }
    """
    package_id = request.get("package_id")
    if not package_id:
        return _make_response(
            "error",
            error=_make_error("MISSING_FIELD", "package_id is required"),
        )

    # Look for manifest
    manifest_path = ROOT / "installed" / package_id / "manifest.json"
    receipt_path = ROOT / "installed" / package_id / "receipt.json"

    if not manifest_path.exists():
        return _make_response(
            "error",
            error=_make_error("PACKAGE_NOT_FOUND", f"Package not found: {package_id}"),
        )

    try:
        manifest = json.loads(manifest_path.read_text())
        receipt = {}
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text())

        return _make_response(
            "ok",
            result={
                "package_id": manifest.get("package_id", package_id),
                "version": manifest.get("version", "0.0.0"),
                "spec_id": manifest.get("spec_id", ""),
                "plane_id": manifest.get("plane_id", ""),
                "package_type": manifest.get("package_type", "standard"),
                "assets": manifest.get("assets", []),
                "assets_count": len(manifest.get("assets", [])),
                "dependencies": manifest.get("dependencies", []),
                "installed_at": receipt.get("installed_at", ""),
                "manifest_hash": receipt.get("manifest_hash", ""),
            },
            evidence={
                "timestamp": _get_timestamp(),
                "input_hash": _hash_json(request),
                "declared_reads": [
                    {"path": str(manifest_path), "type": "manifest"},
                ],
            },
        )
    except json.JSONDecodeError as e:
        return _make_response(
            "error",
            error=_make_error("INVALID_MANIFEST", f"Invalid manifest JSON: {e}"),
        )


def handle_ledger_query(request: Dict[str, Any]) -> Dict[str, Any]:
    """Query ledger entries.

    Request:
        {"operation": "ledger_query"}
        Optional: {"operation": "ledger_query", "type": "governance", "limit": 10}

    Response:
        {
            "status": "ok",
            "result": {
                "entries": [...],
                "ledger_file": "...",
                "count": N
            },
            "evidence": {...}
        }
    """
    ledger_type = request.get("type", "governance")
    limit = request.get("limit", 10)
    event_filter = request.get("event_filter")  # Optional filter by event_type

    # Find ledger file
    ledger_dir = ROOT / "ledger"
    if not ledger_dir.exists():
        return _make_response(
            "error",
            error=_make_error("LEDGER_NOT_FOUND", "No ledger directory"),
        )

    # Find most recent ledger file of requested type
    pattern = f"{ledger_type}-*.jsonl"
    ledger_files = sorted(ledger_dir.glob(pattern), reverse=True)

    if not ledger_files:
        # Try index.jsonl as fallback
        index_path = ledger_dir / "index.jsonl"
        if index_path.exists():
            ledger_files = [index_path]
        else:
            return _make_response(
                "error",
                error=_make_error("LEDGER_NOT_FOUND", f"No {ledger_type} ledger files"),
            )

    ledger_path = ledger_files[0]
    entries = []

    try:
        with open(ledger_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

        for line in all_lines:
            if line.strip():
                try:
                    entry = json.loads(line)
                    # Apply event filter if specified
                    if event_filter:
                        if event_filter.lower() not in entry.get("event_type", "").lower():
                            continue
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue

        # Take last N entries
        entries = entries[-limit:]

        return _make_response(
            "ok",
            result={
                "entries": entries,
                "ledger_file": ledger_path.name,
                "count": len(entries),
                "total_in_file": len(all_lines),
            },
            evidence={
                "timestamp": _get_timestamp(),
                "input_hash": _hash_json(request),
                "declared_reads": [{"path": str(ledger_path), "type": "ledger"}],
            },
        )
    except Exception as e:
        return _make_response(
            "error",
            error=_make_error("LEDGER_READ_ERROR", f"Error reading ledger: {e}"),
        )


def handle_gate_status(request: Dict[str, Any]) -> Dict[str, Any]:
    """Get gate status.

    Request:
        {"operation": "gate_status"}
        Optional: {"operation": "gate_status", "gate": "G1"}

    Response:
        {
            "status": "ok",
            "result": {
                "gates": {...},
                "recent_failures": [...]
            },
            "evidence": {...}
        }
    """
    inspector = _get_inspector()
    gate_filter = request.get("gate")

    # Gate definitions
    gates = {
        "MANIFEST": {
            "phase": "preflight",
            "description": "Basic manifest structure validation",
        },
        "G0A": {
            "phase": "preflight",
            "description": "Package declaration consistency",
        },
        "G0B": {
            "phase": "preflight",
            "description": "Entry point and dependency check",
        },
        "G1": {
            "phase": "preflight",
            "description": "Governance chain validation",
        },
        "OWN": {
            "phase": "preflight",
            "description": "File ownership validation",
        },
        "G3": {
            "phase": "install",
            "description": "Test execution",
        },
        "G4": {
            "phase": "install",
            "description": "Ledger replication",
        },
        "G5": {
            "phase": "install",
            "description": "Signature validation",
        },
    }

    recent_failures = []
    evidence_reads = []

    if inspector:
        failures, evidence = inspector.last_gate_failures(count=5, gate=gate_filter)
        recent_failures = [f.to_dict() for f in failures]
        evidence_reads.append({"path": evidence.path, "hash": evidence.hash})

    return _make_response(
        "ok",
        result={
            "gates": gates,
            "recent_failures": recent_failures,
            "failures_count": len(recent_failures),
        },
        evidence={
            "timestamp": _get_timestamp(),
            "input_hash": _hash_json(request),
            "declared_reads": evidence_reads,
        },
    )


def handle_compliance(request: Dict[str, Any]) -> Dict[str, Any]:
    """Get compliance summary.

    Request:
        {"operation": "compliance"}

    Response:
        {
            "status": "ok",
            "result": {
                "governance_chain": {...},
                "gates": {...},
                "registry_stats": {...}
            },
            "evidence": {...}
        }
    """
    inspector = _get_inspector()
    if not inspector:
        return _make_response(
            "error",
            error=_make_error("INSPECTOR_UNAVAILABLE", "CPInspector not available"),
        )

    # Gather compliance data
    chain, chain_evidence = inspector.get_governance_chain()
    gates, gates_evidence = inspector.get_gate_requirements()
    stats, stats_evidence = inspector.get_registry_stats()
    frameworks, fw_evidence = inspector.list_available_frameworks()
    specs, spec_evidence = inspector.list_available_specs()

    return _make_response(
        "ok",
        result={
            "governance_chain": chain,
            "gates": gates.get("gates", {}),
            "registry_stats": stats,
            "frameworks_count": len(frameworks),
            "specs_count": len(specs),
            "quick_reference": {
                "create_package": "pkgutil init PKG-XXX --spec SPEC-XXX --output _staging/",
                "validate": "pkgutil preflight PKG-XXX --src _staging/PKG-XXX",
                "stage": "pkgutil stage PKG-XXX --src _staging/PKG-XXX",
                "install": "CONTROL_PLANE_ALLOW_UNSIGNED=1 package_install.py --archive _staging/PKG-XXX.tar.gz --id PKG-XXX",
            },
        },
        evidence={
            "timestamp": _get_timestamp(),
            "input_hash": _hash_json(request),
            "declared_reads": [
                {"path": chain_evidence.path, "hash": chain_evidence.hash},
                {"path": stats_evidence.path, "hash": stats_evidence.hash},
            ],
        },
    )


def handle_trace(request: Dict[str, Any]) -> Dict[str, Any]:
    """Trace artifact lineage.

    Request:
        {"operation": "trace", "artifact_id": "FMWK-100"}

    Response:
        {
            "status": "ok",
            "result": {
                "artifact_id": "...",
                "type": "...",
                "data": {...}
            },
            "evidence": {...}
        }
    """
    artifact_id = request.get("artifact_id")
    if not artifact_id:
        return _make_response(
            "error",
            error=_make_error("MISSING_FIELD", "artifact_id is required"),
        )

    # Try to use trace.py
    trace_script = ROOT / "scripts" / "trace.py"
    if not trace_script.exists():
        return _make_response(
            "error",
            error=_make_error("TRACE_UNAVAILABLE", "trace.py script not found"),
        )

    try:
        result = subprocess.run(
            [sys.executable, str(trace_script), "--explain", artifact_id, "--json"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(ROOT),
        )

        if result.returncode != 0:
            return _make_response(
                "error",
                error=_make_error(
                    "TRACE_FAILED",
                    result.stderr.strip() if result.stderr else "Trace failed",
                    details={"artifact_id": artifact_id},
                ),
            )

        if result.stdout:
            try:
                trace_data = json.loads(result.stdout)
                return _make_response(
                    "ok",
                    result={
                        "artifact_id": artifact_id,
                        "type": trace_data.get("type", "unknown"),
                        "data": trace_data.get("data", {}),
                    },
                    evidence={
                        "timestamp": _get_timestamp(),
                        "input_hash": _hash_json(request),
                        "declared_reads": [],  # trace.py handles its own reads
                    },
                )
            except json.JSONDecodeError:
                # Return raw output if not JSON
                return _make_response(
                    "ok",
                    result={
                        "artifact_id": artifact_id,
                        "type": "raw",
                        "data": {"output": result.stdout},
                    },
                    evidence={
                        "timestamp": _get_timestamp(),
                        "input_hash": _hash_json(request),
                        "declared_reads": [],
                    },
                )

        return _make_response(
            "error",
            error=_make_error("TRACE_NO_OUTPUT", "No trace output"),
        )

    except subprocess.TimeoutExpired:
        return _make_response(
            "error",
            error=_make_error("TRACE_TIMEOUT", "Trace timed out"),
        )
    except Exception as e:
        return _make_response(
            "error",
            error=_make_error("TRACE_ERROR", f"Trace error: {e}"),
        )


def handle_signal_status(request: Dict[str, Any]) -> Dict[str, Any]:
    """Get current signal status.

    Request:
        {"operation": "signal_status"}

    Response:
        {
            "status": "ok",
            "result": {
                "signals": {...}
            },
            "evidence": {...}
        }
    """
    # Create default signals bundle
    from modules.shell.interfaces import CPSignalBundle

    signals = CPSignalBundle()

    return _make_response(
        "ok",
        result={
            "signals": {
                "stance": signals.stance,
                "altitude": signals.altitude,
                "turn_number": signals.turn_number,
                "health": signals.health,
                "drift": signals.drift,
                "tier": signals.tier,
                "role": signals.role,
                "active_wo": signals.active_wo,
                "ledger_synced": signals.ledger_synced,
                "gate_state": signals.gate_state,
            },
            "compact_display": signals.to_compact_display(),
        },
        evidence={
            "timestamp": _get_timestamp(),
            "input_hash": _hash_json(request),
            "declared_reads": [],
        },
    )


def handle_manifest_requirements(request: Dict[str, Any]) -> Dict[str, Any]:
    """Get manifest.json field requirements.

    Request:
        {"operation": "manifest_requirements"}

    Response:
        {
            "status": "ok",
            "result": {
                "schema_version": "1.2",
                "required_fields": {...},
                "optional_fields": {...},
                "asset_object": {...},
                "asset_classifications": {...}
            },
            "evidence": {...}
        }
    """
    inspector = _get_inspector()
    if not inspector:
        return _make_response(
            "error",
            error=_make_error("INSPECTOR_UNAVAILABLE", "CPInspector not available"),
        )

    requirements, evidence = inspector.get_manifest_requirements()

    return _make_response(
        "ok",
        result=requirements,
        evidence={
            "timestamp": _get_timestamp(),
            "input_hash": _hash_json(request),
            "declared_reads": [{"path": evidence.path, "hash": evidence.hash}],
        },
    )


def handle_packaging_workflow(request: Dict[str, Any]) -> Dict[str, Any]:
    """Get the complete packaging workflow steps.

    Request:
        {"operation": "packaging_workflow"}

    Response:
        {
            "status": "ok",
            "result": {
                "steps": [...],
                "pkgutil_commands": {...}
            },
            "evidence": {...}
        }
    """
    inspector = _get_inspector()
    if not inspector:
        return _make_response(
            "error",
            error=_make_error("INSPECTOR_UNAVAILABLE", "CPInspector not available"),
        )

    workflow, evidence = inspector.get_packaging_workflow()

    return _make_response(
        "ok",
        result=workflow,
        evidence={
            "timestamp": _get_timestamp(),
            "input_hash": _hash_json(request),
            "declared_reads": [{"path": evidence.path, "hash": evidence.hash}],
        },
    )


def handle_troubleshoot(request: Dict[str, Any]) -> Dict[str, Any]:
    """Get troubleshooting guidance for common errors.

    Request:
        {"operation": "troubleshoot"}
        {"operation": "troubleshoot", "error_type": "G1"}

    Response:
        {
            "status": "ok",
            "result": {
                "troubleshooting": {...}
            },
            "evidence": {...}
        }
    """
    inspector = _get_inspector()
    if not inspector:
        return _make_response(
            "error",
            error=_make_error("INSPECTOR_UNAVAILABLE", "CPInspector not available"),
        )

    error_type = request.get("error_type")
    guide, evidence = inspector.get_troubleshooting_guide(error_type)

    return _make_response(
        "ok",
        result=guide,
        evidence={
            "timestamp": _get_timestamp(),
            "input_hash": _hash_json(request),
            "declared_reads": [{"path": evidence.path, "hash": evidence.hash}],
        },
    )


def handle_example_manifest(request: Dict[str, Any]) -> Dict[str, Any]:
    """Get an example manifest.json for a package type.

    Request:
        {"operation": "example_manifest"}
        {"operation": "example_manifest", "package_type": "agent"}

    Response:
        {
            "status": "ok",
            "result": {
                "example": {...},
                "note": "..."
            },
            "evidence": {...}
        }
    """
    inspector = _get_inspector()
    if not inspector:
        return _make_response(
            "error",
            error=_make_error("INSPECTOR_UNAVAILABLE", "CPInspector not available"),
        )

    package_type = request.get("package_type", "library")
    example, evidence = inspector.get_example_manifest(package_type)

    return _make_response(
        "ok",
        result=example,
        evidence={
            "timestamp": _get_timestamp(),
            "input_hash": _hash_json(request),
            "declared_reads": [{"path": evidence.path, "hash": evidence.hash}],
        },
    )


def handle_list_frameworks(request: Dict[str, Any]) -> Dict[str, Any]:
    """List all registered frameworks.

    Request:
        {"operation": "list_frameworks"}

    Response:
        {
            "status": "ok",
            "result": {
                "frameworks": [...],
                "count": N
            },
            "evidence": {...}
        }
    """
    inspector = _get_inspector()
    if not inspector:
        return _make_response(
            "error",
            error=_make_error("INSPECTOR_UNAVAILABLE", "CPInspector not available"),
        )

    frameworks, evidence = inspector.list_available_frameworks()

    return _make_response(
        "ok",
        result={
            "frameworks": frameworks,
            "count": len(frameworks),
        },
        evidence={
            "timestamp": _get_timestamp(),
            "input_hash": _hash_json(request),
            "declared_reads": [{"path": evidence.path, "hash": evidence.hash}],
        },
    )


def handle_list_specs(request: Dict[str, Any]) -> Dict[str, Any]:
    """List registered specs, optionally filtered by framework.

    Request:
        {"operation": "list_specs"}
        {"operation": "list_specs", "framework_id": "FMWK-100"}

    Response:
        {
            "status": "ok",
            "result": {
                "specs": [...],
                "count": N
            },
            "evidence": {...}
        }
    """
    inspector = _get_inspector()
    if not inspector:
        return _make_response(
            "error",
            error=_make_error("INSPECTOR_UNAVAILABLE", "CPInspector not available"),
        )

    framework_id = request.get("framework_id")
    specs, evidence = inspector.list_available_specs(framework_id)

    return _make_response(
        "ok",
        result={
            "specs": specs,
            "count": len(specs),
            "filter": {"framework_id": framework_id} if framework_id else None,
        },
        evidence={
            "timestamp": _get_timestamp(),
            "input_hash": _hash_json(request),
            "declared_reads": [{"path": evidence.path, "hash": evidence.hash}],
        },
    )


def handle_spec_info(request: Dict[str, Any]) -> Dict[str, Any]:
    """Get the manifest for a specific spec.

    Request:
        {"operation": "spec_info", "spec_id": "SPEC-CORE-001"}

    Response:
        {
            "status": "ok",
            "result": {
                "spec_id": "...",
                "manifest": {...}
            },
            "evidence": {...}
        }
    """
    spec_id = request.get("spec_id")
    if not spec_id:
        return _make_response(
            "error",
            error=_make_error("MISSING_FIELD", "spec_id is required"),
        )

    inspector = _get_inspector()
    if not inspector:
        return _make_response(
            "error",
            error=_make_error("INSPECTOR_UNAVAILABLE", "CPInspector not available"),
        )

    manifest, evidence = inspector.get_spec_manifest(spec_id)

    if manifest is None:
        return _make_response(
            "error",
            error=_make_error("SPEC_NOT_FOUND", f"Spec not found: {spec_id}"),
        )

    return _make_response(
        "ok",
        result={
            "spec_id": spec_id,
            "manifest": manifest,
        },
        evidence={
            "timestamp": _get_timestamp(),
            "input_hash": _hash_json(request),
            "declared_reads": [{"path": evidence.path, "hash": evidence.hash}],
        },
    )


def handle_governed_roots(request: Dict[str, Any]) -> Dict[str, Any]:
    """List governed roots from config.

    Request:
        {"operation": "governed_roots"}

    Response:
        {
            "status": "ok",
            "result": {
                "roots": [...],
                "count": N
            },
            "evidence": {...}
        }
    """
    inspector = _get_inspector()
    if not inspector:
        return _make_response(
            "error",
            error=_make_error("INSPECTOR_UNAVAILABLE", "CPInspector not available"),
        )

    roots, evidence = inspector.list_governed_roots()

    return _make_response(
        "ok",
        result={
            "roots": roots,
            "count": len(roots),
        },
        evidence={
            "timestamp": _get_timestamp(),
            "input_hash": _hash_json(request),
            "declared_reads": [{"path": evidence.path, "hash": evidence.hash}],
        },
    )


def handle_explain_path(request: Dict[str, Any]) -> Dict[str, Any]:
    """Explain path classification (PRISTINE/DERIVED/APPEND_ONLY).

    Request:
        {"operation": "explain_path", "path": "lib/authz.py"}

    Response:
        {
            "status": "ok",
            "result": {
                "path": "...",
                "classification": "PRISTINE|DERIVED|APPEND_ONLY|UNKNOWN",
                "governed_root": "...",
                "explanation": "..."
            },
            "evidence": {...}
        }
    """
    path = request.get("path")
    if not path:
        return _make_response(
            "error",
            error=_make_error("MISSING_FIELD", "path is required"),
        )

    inspector = _get_inspector()
    if not inspector:
        return _make_response(
            "error",
            error=_make_error("INSPECTOR_UNAVAILABLE", "CPInspector not available"),
        )

    classification, evidence = inspector.explain_path(path)

    return _make_response(
        "ok",
        result=classification.to_dict(),
        evidence={
            "timestamp": _get_timestamp(),
            "input_hash": _hash_json(request),
            "declared_reads": [{"path": evidence.path, "hash": evidence.hash}],
        },
    )


def handle_execute_command(request: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a shell command.

    Request:
        {"operation": "execute_command", "command": "pkg"}

    This routes to interactive shell commands like :pkg, :ledger, etc.

    Response:
        {
            "status": "ok",
            "result": {
                "command": "...",
                "executed": true/false,
                "note": "..."
            },
            "evidence": {...}
        }
    """
    command = request.get("command")
    if not command:
        return _make_response(
            "error",
            error=_make_error("MISSING_FIELD", "command is required"),
        )

    # Map command to appropriate operation
    command_mapping = {
        "pkg": "pkg_list",
        "packages": "pkg_list",
        "ledger": "ledger_query",
        "gate": "gate_status",
        "gates": "gate_status",
        "compliance": "compliance",
        "signals": "signal_status",
        "sig": "signal_status",
    }

    command_lower = command.lower().strip()

    # Check if this is a mapped command
    if command_lower in command_mapping:
        operation = command_mapping[command_lower]
        handler = {
            "pkg_list": handle_pkg_list,
            "ledger_query": handle_ledger_query,
            "gate_status": handle_gate_status,
            "compliance": handle_compliance,
            "signal_status": handle_signal_status,
        }.get(operation)

        if handler:
            return handler(request)

    # Check if command has arguments (e.g., "pkg PKG-TEST-001")
    parts = command.split(None, 1)
    cmd_name = parts[0].lower() if parts else ""
    cmd_args = parts[1] if len(parts) > 1 else ""

    if cmd_name == "pkg" and cmd_args:
        return handle_pkg_info({"operation": "pkg_info", "package_id": cmd_args})

    if cmd_name == "trace" and cmd_args:
        return handle_trace({"operation": "trace", "artifact_id": cmd_args})

    # Command not recognized - provide hint
    return _make_response(
        "ok",
        result={
            "command": command,
            "executed": False,
            "note": "Command not recognized for pipe mode. Use operation directly.",
            "available_operations": list(command_mapping.keys()),
        },
        evidence={
            "timestamp": _get_timestamp(),
            "input_hash": _hash_json(request),
            "declared_reads": [],
        },
    )
