"""HO3 tier test configuration. Ensures kernel and HO3 libs are importable."""
import sys
from pathlib import Path

# HO3/tests/ → HO3/ → Control_Plane_v2/
HO3_ROOT = Path(__file__).resolve().parent.parent
CP_ROOT = HO3_ROOT.parent
HOT_ROOT = CP_ROOT / "HOT"

sys.path.insert(0, str(HO3_ROOT))
sys.path.insert(0, str(HOT_ROOT))
