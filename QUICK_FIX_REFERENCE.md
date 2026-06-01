📋 QUICK FIX REFERENCE - Screenshots & Controls

═══════════════════════════════════════════════════════════════════════════════

🚀 FASTEST DEPLOYMENT (2 minutes):

1. Run database fix:
   cd C:\ServerMonitor
   python fix_screenshots_and_controls.py

2. Restart portal:
   Stop-Process -Name python -Force
   python run_portal.py

3. Restart agent:
   Restart-Service ServerMonitorAgent -Force

4. Wait 30 seconds, check portal - screenshots should appear in 5-15 minutes

═══════════════════════════════════════════════════════════════════════════════

🤖 AUTOMATED DEPLOYMENT (PowerShell):

Run as Administrator:
   .\Deploy-ScreenshotFix.ps1

With diagnostics:
   .\Deploy-ScreenshotFix.ps1 -RunDiagnostics

═══════════════════════════════════════════════════════════════════════════════

✅ VERIFICATION:

Run diagnostic test:
   python diagnostic_test.py

Check database:
   SELECT COUNT(*) FROM screenshot;
   SELECT screenshot_enabled, COUNT(*) FROM server GROUP BY screenshot_enabled;

Check agent logs:
   C:\Program Files\ServerMonitor\Agent\agent.log

Check screenshot directory:
   dir C:\ServerMonitor\data\screenshots\

═══════════════════════════════════════════════════════════════════════════════

📖 FILES MODIFIED:

✓ agent.py
  - ENABLE_SCREENSHOTS = True (line 53)
  - Improved command handling (line 337+)
  - Better error logging

✓ web/models.py
  - screenshot_enabled default=True (line 150)

✓ NEW: fix_screenshots_and_controls.py
  - Database fix utility

✓ NEW: diagnostic_test.py
  - System verification

✓ NEW: Deploy-ScreenshotFix.ps1
  - Automated deployment

═══════════════════════════════════════════════════════════════════════════════

🎯 WHAT CHANGED:

BEFORE:
❌ ENABLE_SCREENSHOTS = False (disabled)
❌ screenshot_enabled defaults to False (disabled)
❌ Weak command error handling
❌ Portal shows no screenshots

AFTER:
✅ ENABLE_SCREENSHOTS = True (enabled)
✅ screenshot_enabled defaults to True (enabled)
✅ Robust command handling with error details
✅ Portal displays all screenshots
✅ Remote commands execute properly

═══════════════════════════════════════════════════════════════════════════════

⏱️ TIMELINE:

0s     - Fix applied
30s    - Agents connect
60s    - Metrics received
5min   - First screenshot captured (configurable)
10min  - Screenshots visible in portal

═══════════════════════════════════════════════════════════════════════════════

❌ IF NOT WORKING:

1. Check ENABLE_SCREENSHOTS in agent startup logs
   Look for: "🚀 Starting ServerMonitor Enterprise Agent"
   Should see: ENABLE_SCREENSHOTS = True

2. Check screenshots being captured
   Look for: "📸 Capturing screenshot"
   Check: C:\ServerMonitor\data\screenshots\

3. Check database
   ```
   SELECT * FROM server WHERE api_key='your-agent-key';
   ```
   screenshot_enabled should be 1 (TRUE)

4. Test metrics endpoint
   ```powershell
   $payload = @{ api_key='key'; metrics=@{cpu_percent=25} } | ConvertTo-Json
   Invoke-WebRequest -Uri 'http://localhost:5000/api/v2/agent/metrics' -Method Post -Body $payload
   ```

5. Run diagnostics
   ```
   python diagnostic_test.py
   ```

═══════════════════════════════════════════════════════════════════════════════

🆘 COMMON ISSUES:

Q: Portal still shows no screenshots after 15 minutes
A: Check agent logs for "📸 Capturing screenshot"
   If not present, check database: SELECT screenshot_enabled FROM server;

Q: Agent not appearing online
A: Check firewall - agent must reach SERVER_URL
   Check logs: "✗ Connection error"

Q: Commands not executing
A: Check agent logs for "▶️ Executing command"
   Check X-Agent-Key header is valid
   Verify command isn't timed out (120s limit)

Q: Software detection not working
A: This uses same metrics endpoint, check if metrics working first
   Software collection has 5-minute cache

═══════════════════════════════════════════════════════════════════════════════

📞 SUPPORT LOGS:

Agent logs:
  C:\Program Files\ServerMonitor\Agent\agent.log

Server logs:
  C:\ServerMonitor\logs\

Portal logs:
  Browser console (F12) → Console tab

Database logs:
  SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 20;

═══════════════════════════════════════════════════════════════════════════════

🔄 ROLLBACK (if needed):

Edit agent.py line 53:
  ENABLE_SCREENSHOTS = False

OR database:
  UPDATE server SET screenshot_enabled = 0;

All changes are safe and non-destructive.
No data is deleted.

═══════════════════════════════════════════════════════════════════════════════

✨ Version: 2.0.0-HOTFIX | Status: ✅ PRODUCTION READY
