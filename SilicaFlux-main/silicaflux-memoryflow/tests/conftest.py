import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

HAVE_VERILATOR = shutil.which("verilator") is not None
HAVE_YOSYS = shutil.which("yosys") is not None

needs_verilator = pytest.mark.skipif(not HAVE_VERILATOR, reason="verilator not installed")
needs_yosys = pytest.mark.skipif(not HAVE_YOSYS, reason="yosys not installed")
