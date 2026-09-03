#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from web.routes.api import agent_metrics
    print("✓ Agent metrics function imported successfully")
except Exception as e:
    print(f"✗ Failed to import agent_metrics: {e}")
    import traceback
    traceback.print_exc()
