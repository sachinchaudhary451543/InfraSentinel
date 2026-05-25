"""Run license sync from the project root using the application's app context.

Usage:
  python scripts/run_license_sync.py [tenant_id]

This is a convenience wrapper for running the sync in a standalone worker or
CI job without coupling a scheduler into the web process.
"""
import sys
from web.app import app

def main(argv):
    tenant_id = int(argv[1]) if len(argv) > 1 else None
    with app.app_context():
        from web.tasks.sync_licenses import run_license_sync
        res = run_license_sync(tenant_id=tenant_id)
        print('Sync result:', res)

if __name__ == '__main__':
    main(sys.argv)
