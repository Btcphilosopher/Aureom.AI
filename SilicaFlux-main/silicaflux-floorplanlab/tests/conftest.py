import shutil
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "python"))

from floorplanlab.config import tool_env  # noqa: E402


def tools_available() -> bool:
    env = tool_env()
    return all(Path(env.get(k, "/nonexistent")).exists() for k in ("OPENROAD_EXE", "YOSYS_EXE", "ORFS_FLOW"))


requires_tools = pytest.mark.skipif(not tools_available(), reason="OpenROAD/Yosys/ORFS not installed (env/install_toolchain.sh)")


@pytest.fixture
def project():
    return PROJECT


TECH_LEF = """
VERSION 5.8 ;
UNITS
  DATABASE MICRONS 1000 ;
END UNITS
MANUFACTURINGGRID 0.005 ;
LAYER Metal1
  TYPE ROUTING ;
  DIRECTION HORIZONTAL ;
  PITCH 0.5 ;
  WIDTH 0.2 ;
END Metal1
LAYER Via1
  TYPE CUT ;
END Via1
LAYER Metal2
  TYPE ROUTING ;
  DIRECTION VERTICAL ;
  PITCH 0.5 ;
  WIDTH 0.2 ;
END Metal2
LAYER Metal3
  TYPE ROUTING ;
  DIRECTION HORIZONTAL ;
  PITCH 1.0 ;
  WIDTH 0.4 ;
END Metal3
VIA V12 DEFAULT
  LAYER Metal1 ;
    RECT -0.1 -0.1 0.1 0.1 ;
  LAYER Via1 ;
    RECT -0.1 -0.1 0.1 0.1 ;
END V12
SITE core
  CLASS CORE ;
  SIZE 0.5 BY 4.0 ;
END core
MACRO TIEHI
  CLASS CORE ;
  SIZE 1 BY 4 ;
  SITE core ;
  PIN H
    DIRECTION OUTPUT ;
    PORT
      LAYER Metal1 ;
        RECT 0 0 0.2 0.2 ;
    END
  END H
END TIEHI
MACRO RAM
  CLASS BLOCK ;
  SIZE 100 BY 50 ;
  SYMMETRY X Y ;
  PIN D[0]
    DIRECTION INPUT ;
    USE SIGNAL ;
    PORT
      LAYER Metal2 ;
        RECT 10 0 10.2 0.3 ;
    END
  END D[0]
  PIN VDD!
    DIRECTION INOUT ;
    USE POWER ;
    PORT
      LAYER Metal3 ;
        RECT 1 0 3 12 ;
        RECT 5 0 7 50 ;
    END
  END VDD!
  PIN VSS!
    DIRECTION INOUT ;
    USE GROUND ;
    PORT
      LAYER Metal3 ;
        RECT 8 0 10 50 ;
    END
  END VSS!
  OBS
    LAYER Metal1 ;
      RECT 0 0 100 50 ;
  END
END RAM
"""


@pytest.fixture
def tech_lef(tmp_path):
    p = tmp_path / "t.lef"
    p.write_text(TECH_LEF)
    return p


@pytest.fixture
def which():
    return shutil.which
