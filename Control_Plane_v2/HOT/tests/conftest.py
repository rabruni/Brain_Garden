"""HOT tier test configuration. Ensures kernel is importable."""
import sys
from pathlib import Path

# HOT/tests/ → HOT/ (parent.parent = HOT)
HOT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HOT_ROOT))
