from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOT = _HERE.parent

if (_HOT / "kernel" / "ledger_client.py").exists():
    _ROOT = _HOT.parent
    sys.path.insert(0, str(_HOT / "admin"))
    for p in [_HOT / "kernel", _HOT / "scripts", _HOT]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
else:
    _STAGING_ROOT = _HERE.parents[2]
    sys.path.insert(0, str(_STAGING_ROOT / "PKG-ADMIN-001" / "HOT" / "admin"))
    for p in [
        _STAGING_ROOT / "PKG-KERNEL-001" / "HOT" / "kernel",
        _STAGING_ROOT / "PKG-KERNEL-001" / "HOT",
    ]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

from forensic_policy import DEFAULT_POLICY, ForensicPolicy


def test_default_verbosity_full():
    assert ForensicPolicy().verbosity == "full"


def test_default_include_prompts_true():
    assert ForensicPolicy().include_prompts is True


def test_default_max_bytes():
    assert ForensicPolicy().max_bytes == 500_000


def test_override_verbosity():
    assert ForensicPolicy(verbosity="compact").verbosity == "compact"


def test_truncation_marker_format():
    assert "{bytes}" in ForensicPolicy().truncation_marker


def test_default_policy_singleton():
    assert DEFAULT_POLICY == ForensicPolicy()
