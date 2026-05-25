"""Compute productivity metrics from raw activity events.

Expect an input list of activity events per employee with fields:
 - timestamp (unix seconds or ISO string parseable by float())
 - duration_seconds (int)
 - activity_type: one of 'active', 'idle', 'neutral'
 - application: executable or website string

The module exposes `aggregate_productivity(events)` which returns totals and
breakdowns suitable for feeding the dashboard.
"""
from typing import List, Dict, Any
from collections import defaultdict, Counter
import math


def _to_seconds(v):
    try:
        return int(v)
    except Exception:
        return 0


def seconds_to_hm(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h {m}m"


def aggregate_productivity(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate a list of events into productivity summary.

    events: Each event must include duration_seconds and activity_type.
    activity_type mapping:
      - 'active' => desk time (system online and user active)
      - 'idle' => idle time (system online but user idle)
      - 'neutral' => neutral (unknown/other)

    Productive vs non-productive classification is not handled here; caller should
    supply application classification via `classify_application` if needed.
    """
    totals = defaultdict(int)
    app_counter = Counter()

    for e in events:
        dur = _to_seconds(e.get('duration_seconds', 0))
        typ = e.get('activity_type', 'neutral')
        totals[typ] += dur
        app = e.get('application')
        if app:
            app_counter[app] += dur

    desk = totals.get('active', 0)
    idle = totals.get('idle', 0)
    neutral = totals.get('neutral', 0)
    total_time = desk + idle + neutral

    # Simple productive/non-productive split: assume 'active' is productive.
    # In practice you'd map apps to productive/non-productive categories.
    productive = desk
    non_productive = 0

    summary = {
        'total_seconds': total_time,
        'desk_seconds': desk,
        'idle_seconds': idle,
        'productive_seconds': productive,
        'non_productive_seconds': non_productive,
        'neutral_seconds': neutral,
        'total': seconds_to_hm(total_time),
        'desk': seconds_to_hm(desk),
        'idle': seconds_to_hm(idle),
        'productive': seconds_to_hm(productive),
        'non_productive': seconds_to_hm(non_productive),
        'neutral': seconds_to_hm(neutral),
        'most_used_apps': [ {'app': a, 'seconds': s} for a, s in app_counter.most_common(10) ]
    }

    return summary
