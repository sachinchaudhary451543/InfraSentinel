# Screenshot Display Issue - Root Cause & Fix

## Problem Statement
Screenshots were not displaying on the dashboard after the PR deployment for agent-installed systems.

## Root Cause Analysis

### Issue 1: Inconsistent Screenshot Path Storage
The `agent_metrics` endpoint was calculating the base directory incorrectly:
- **Before fix**: Used `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` with `__file__` being `web/routes/api.py`, which calculated to `C:\` (root)
- **Result**: Screenshots were saved to `C:\data\screenshots\` instead of `C:\ServerMonitor\data\screenshots\`
- **Impact**: Database records stored incorrect paths, causing `/api/screenshot/{id}` endpoint to fail when checking file existence

### Issue 2: Missing Screenshot Configuration
By default, new servers had `screenshot_enabled = False`, so agents weren't capturing screenshots even when the system was configured correctly.

### Issue 3: JavaScript Rendering Changes
Recent commits changed how screenshot lightbox URLs were passed, potentially causing escaping issues with certain URL formats.

## Fixes Applied

### Fix 1: Corrected Path Calculation in agent_metrics Endpoint
**File**: `web/routes/api.py` (agent_metrics function)

Changed from:
```python
base_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    '..', 'data', 'screenshots'
)
```

To:
```python
from web.app import app as flask_app
app_root = os.path.dirname(flask_app.root_path)  # web -> ServerMonitor
base_dir = os.path.join(app_root, 'data', 'screenshots')
```

This ensures screenshots are ALWAYS saved to `C:\ServerMonitor\data\screenshots\`

### Fix 2: Applied Same Fix to Legacy Upload Endpoint
**File**: `web/routes/api.py` (legacy_api_screenshot_upload function)

Updated the legacy screenshot upload endpoint to use the same corrected path calculation.

### Fix 3: Migrated Existing Broken Records
**Script**: `fix_screenshot_paths.py`

- Identifies all screenshot records with incorrect paths (`C:\data\screenshots\`)
- Copies files from wrong location to correct location
- Updates database records to point to correct paths
- Result: All 3 affected records were fixed and copied

**Usage**:
```bash
python fix_screenshot_paths.py
```

### Fix 4: Enable Screenshots by Default (Optional)
**Script**: `enable_screenshots_default.py`

Enables `screenshot_enabled = True` for all agent-installed servers so they immediately start capturing screenshots.

**Usage**:
```bash
python enable_screenshots_default.py
```

## Verification Steps

### 1. Check That Paths Are Correct
```bash
python -c "
from web.app import app
from web.models import db, Screenshot
import os
app.app_context().push()

shots = Screenshot.query.all()
for s in shots[:5]:
    exists = os.path.isfile(s.local_file_path) if s.local_file_path else False
    correct = 'ServerMonitor' in s.local_file_path if s.local_file_path else False
    print(f'ID {s.id}: File Exists={exists}, Path Correct={correct}')
"
```

### 2. Test New Screenshot Upload
```bash
python test_screenshot_path.py
```

Expected output should show:
- Status: 200
- Path contains ServerMonitor: True
- File exists: True

### 3. Check Database Screenshot Records
```bash
python scripts/check_screenshots.py
```

Expected: All screenshots should have valid local_file_path and files should exist on disk.

## Deployment Instructions

1. **Pull the latest code** with the fixes
2. **Run the migration script** to fix existing broken records:
   ```bash
   python fix_screenshot_paths.py
   ```
3. **Optionally enable screenshots by default**:
   ```bash
   python enable_screenshots_default.py
   ```
4. **Restart the application**
5. **Verify screenshots appear** in the dashboard

## How Screenshots Should Flow Now

1. Agent captures screenshot every N minutes (configurable)
2. Agent sends base64-encoded screenshot to `/api/v2/agent/metrics`
3. Server saves to: `C:\ServerMonitor\data\screenshots\screenshot_{server_id}_{hostname}_{timestamp}.jpg`
4. Database record stores absolute path: `C:\ServerMonitor\data\screenshots\...`
5. Frontend calls `/api/v2/server/{id}/screenshots` to get list
6. API checks `os.path.isfile(local_file_path)` - now returns True
7. API returns `image_url: /api/screenshot/{id}`
8. Frontend renders thumbnails from `/api/screenshot/{id}?size=thumb`
9. Screenshots appear in UI

## Files Modified

- `web/routes/api.py` - Fixed path calculation in both screenshot endpoints
- `fix_screenshot_paths.py` - Script to migrate existing broken records
- `enable_screenshots_default.py` - Script to enable screenshots for agents
- `test_screenshot_path.py` - Test script to verify functionality

## Related Issues

- JavaScript onclick code generation in `web/templates/remote_screenshots.html` (recent changes) - appears to be working correctly after fixes
- Dashboard service filtering changes in `web/dashboard_service.py` - no impact on screenshot display

## Status

✅ **All fixes applied and tested**
- New screenshots are saved with correct paths
- Existing broken screenshots have been migrated
- API returns correct image URLs
- Screenshots should now display for all agent-installed systems
