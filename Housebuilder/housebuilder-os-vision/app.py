"""Housebuilder.OS Vision - Streamlit entry point.

Run from the project root::

    streamlit run app.py

Views: Images · Twin · Quantities · Costs · Scenarios (see ``housebuilder_vision/ui``).
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from housebuilder_vision.ui.app import main  # noqa: E402

main()
