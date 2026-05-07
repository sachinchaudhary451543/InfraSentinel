"""Check screenshots DB records and local file availability.
Run from repository root inside the virtualenv:

python scripts/check_screenshots.py

This script prints:
 - total screenshots
 - screenshots with missing local_file_path
 - screenshots where local_file_path is set but file missing
 - screenshots with neither local_file_path nor sharepoint_url
"""
import os
import sys

# Ensure repo root is on path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from web.app import app
from web.models import db, Screenshot

with app.app_context():
    shots = Screenshot.query.all()
    total = len(shots)
    missing_local_path = []
    missing_file_on_disk = []
    missing_both = []

    for s in shots:
        lp = s.local_file_path
        sp = s.sharepoint_url
        if not lp:
            if not sp:
                missing_both.append((s.id, s.filename))
            else:
                missing_local_path.append((s.id, s.filename, 'sharepoint_only'))
        else:
            if not os.path.exists(lp):
                missing_file_on_disk.append((s.id, s.filename, lp))

    print(f"Total screenshots: {total}")
    print(f"Records with sharepoint_url but no local_file_path: {len(missing_local_path)}")
    if missing_local_path:
        for r in missing_local_path[:10]:
            print("  ", r)
    print(f"Records with local_file_path set but file missing on disk: {len(missing_file_on_disk)}")
    if missing_file_on_disk:
        for r in missing_file_on_disk[:10]:
            print("  ", r)
    print(f"Records missing both local_file_path and sharepoint_url: {len(missing_both)}")
    if missing_both:
        for r in missing_both[:10]:
            print("  ", r)

    # Exit with non-zero code if any critical missing records exist
    if missing_both or missing_file_on_disk:
        sys.exit(2)
    else:
        sys.exit(0)
