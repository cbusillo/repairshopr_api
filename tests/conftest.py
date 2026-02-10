from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNC_ROOT = ROOT / "repairshopr_sync"

if str(SYNC_ROOT) not in sys.path:
    sys.path.insert(0, str(SYNC_ROOT))
