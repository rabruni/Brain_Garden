"""Backward-compatibility shim. Real implementation at HOT/kernel/."""
import sys
import importlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "HOT"))
_real = importlib.import_module("kernel.atomic")
# Re-export everything from the real module
globals().update({k: v for k, v in _real.__dict__.items()})
