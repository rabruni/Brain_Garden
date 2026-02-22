"""Holdout scenario runner (T-006)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from factory.models import HoldoutResult, HoldoutScenario, ProductSpec


def _run_bash(script: str, cwd: str, timeout: int = 60) -> tuple[int, str, str]:
    """Run a bash script, return (exit_code, stdout, stderr)."""
    if not script.strip():
        return 0, "", ""
    try:
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Timeout after {timeout}s"
    except Exception as e:
        return -2, "", str(e)


def _derive_responsible_task(
    holdout: HoldoutScenario, spec: ProductSpec
) -> str:
    """Derive the D8 task responsible for this holdout's validated scenarios."""
    # holdout.validates → scenario IDs → find D8 task that covers those scenarios
    for task in spec.tasks.tasks:
        for sc_id in holdout.validates:
            if sc_id in task.scenarios_satisfied:
                return task.id
    return "UNKNOWN"


def run_holdouts(
    spec: ProductSpec,
    install_root: str | Path,
    timeout: int = 60,
) -> list[HoldoutResult]:
    """Execute D9 holdout scenarios against installed code.

    Runs Setup → Execute → Verify for each scenario.
    P0 scenarios run first. Exit 0 = PASS, non-zero = FAIL, exception = ERROR.
    """
    root = str(Path(install_root))
    results: list[HoldoutResult] = []

    # Sort: P0 first, then P1, then P2
    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    sorted_scenarios = sorted(
        spec.holdouts.scenarios,
        key=lambda h: (priority_order.get(h.priority, 9), h.id),
    )

    for holdout in sorted_scenarios:
        responsible = _derive_responsible_task(holdout, spec)

        try:
            # Setup
            if holdout.setup:
                exit_code, _, stderr = _run_bash(holdout.setup, root, timeout)
                if exit_code != 0:
                    results.append(HoldoutResult(
                        holdout_id=holdout.id,
                        priority=holdout.priority,
                        status="ERROR",
                        validates_scenarios=list(holdout.validates),
                        validates_contracts=list(holdout.contracts),
                        responsible_task=responsible,
                        error_message=f"Setup failed (exit {exit_code}): {stderr[:300]}",
                    ))
                    continue

            # Execute
            if holdout.execute:
                exit_code, stdout, stderr = _run_bash(holdout.execute, root, timeout)
                if exit_code != 0:
                    results.append(HoldoutResult(
                        holdout_id=holdout.id,
                        priority=holdout.priority,
                        status="ERROR",
                        validates_scenarios=list(holdout.validates),
                        validates_contracts=list(holdout.contracts),
                        responsible_task=responsible,
                        error_message=f"Execute failed (exit {exit_code}): {stderr[:300]}",
                    ))
                    continue

            # Verify
            if holdout.verify:
                exit_code, stdout, stderr = _run_bash(holdout.verify, root, timeout)
                if exit_code == 0:
                    status = "PASS"
                else:
                    status = "FAIL"
                results.append(HoldoutResult(
                    holdout_id=holdout.id,
                    priority=holdout.priority,
                    status=status,
                    validates_scenarios=list(holdout.validates),
                    validates_contracts=list(holdout.contracts),
                    responsible_task=responsible,
                    actual_output=stdout[:500] if status == "FAIL" else "",
                    expected_output="Exit code 0" if status == "FAIL" else "",
                    error_message=stderr[:300] if status == "FAIL" else "",
                ))
            else:
                # No verify step — assume PASS
                results.append(HoldoutResult(
                    holdout_id=holdout.id,
                    priority=holdout.priority,
                    status="PASS",
                    validates_scenarios=list(holdout.validates),
                    validates_contracts=list(holdout.contracts),
                    responsible_task=responsible,
                ))

        except Exception as e:
            results.append(HoldoutResult(
                holdout_id=holdout.id,
                priority=holdout.priority,
                status="ERROR",
                validates_scenarios=list(holdout.validates),
                validates_contracts=list(holdout.contracts),
                responsible_task=responsible,
                error_message=str(e)[:500],
            ))

        # Cleanup (best-effort, don't fail on cleanup errors)
        if holdout.cleanup:
            try:
                _run_bash(holdout.cleanup, root, timeout=30)
            except Exception:
                pass

    return results
