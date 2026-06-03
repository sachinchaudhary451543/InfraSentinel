# Quick Deployment Guide - Dashboard Socket.IO & Mobile Fixes

**Date**: June 1, 2026  
**Deployment Time**: ~5 minutes  
**Rollback Time**: ~2 minutes  
**Risk Level**: LOW (No backend changes, pure frontend fixes)

---

## Pre-Deployment Checklist

- [ ] Read IMPLEMENTATION_COMPLETE.md
- [ ] Verify verification script passes: `python verify_dashboard_fixes.py`
- [ ] Test in staging environment (if available)
- [ ] Backup current dashboard.html: `cp web/templates/dashboard.html web/templates/dashboard.html.bak`
- [ ] Have rollback files ready

---

## Deployment Steps

### Step 1: Verify Files Exist (30 seconds)

```powershell
# Windows/PowerShell
Test-Path "c:\ServerMonitor\web\static\css\dashboard_mobile_fixes.css"
Test-Path "c:\ServerMonitor\web\static\js\dashboard_socket_fix.js"
```

**Expected**: Both should return `True`

### Step 2: Run Verification Script (1 minute)

```bash
cd c:\ServerMonitor
python verify_dashboard_fixes.py
```

**Expected**: Should show "✅ ALL CHECKS PASSED"

### Step 3: Restart Flask Server (2-3 minutes)

```bash
# Option A: Windows Service
net stop servermonitor
net start servermonitor

# Option B: Manual restart
# 1. Kill Flask process (Ctrl+C)
# 2. Restart: python main.py

# Option C: Systemd (Linux/Docker)
systemctl restart servermonitor
```

**Wait for**: Server to fully start (watch logs)

### Step 4: Verify Deployment (1-2 minutes)

#### Check 1: Browser Cache Clear
```
In each browser:
- Hard refresh: Ctrl+Shift+R (Windows/Linux) or Cmd+Shift+R (Mac)
- DevTools → Application → Cache Storage → Clear
```

#### Check 2: Open Dashboard
- Navigate to: `http://localhost:5000/` (or production URL)
- Look for green dot in bottom-right corner (Socket status indicator)
- Watch browser console (F12) for `[Dashboard]` logs

#### Check 3: Verify CSS Loaded
```javascript
// In browser console:
document.querySelector('link[href*="dashboard_mobile_fixes"]')
// Should return <link> element, not null
```

#### Check 4: Verify JS Loaded
```javascript
// In browser console:
typeof window.DashboardSocketManager
// Should return 'object', not 'undefined'

typeof window.ChartResponsivityManager
// Should return 'object', not 'undefined'
```

#### Check 5: Socket Connection
```javascript
// In browser console:
window.DashboardSocketManager.isConnected()
// Should return true (or become true within 10s)
```

---

## Testing After Deployment

### 5-Minute Quick Test
```
✓ Open dashboard in Chrome desktop
✓ Verify green dot appears (bottom-right)
✓ Watch metrics update (should show new values every 5-8s)
✓ No errors in console (F12)
✓ Open on phone/tablet → should look reasonable
```

### 15-Minute Comprehensive Test
```
✓ Desktop: Chrome, Firefox, Safari (if Mac)
✓ Mobile: iPhone, Android phone
✓ Test filter/search functionality
✓ Rotate mobile device → charts should resize
✓ Monitor metrics for 5+ minutes → should update consistently
✓ Check network tab: Dashboard file loads
✓ Check network tab: No 404 errors
```

### 30-Minute Network Resilience Test (Optional)
```
✓ Open DevTools Network tab
✓ Throttle to "Slow 3G"
✓ Watch for Socket.IO reconnection attempts
✓ Verify automatic reconnection works
✓ Verify metrics resume after reconnection
```

---

## Verification Commands

### Test File Sizes
```powershell
(Get-Item "web\static\css\dashboard_mobile_fixes.css").Length
(Get-Item "web\static\js\dashboard_socket_fix.js").Length
```

**Expected**:
- CSS: ~10,000-11,000 bytes
- JS: ~15,000-16,000 bytes

### Test File Availability
```powershell
# Check if files are accessible via web server
Invoke-WebRequest "http://localhost:5000/static/css/dashboard_mobile_fixes.css" -Method Head -ErrorAction SilentlyContinue
Invoke-WebRequest "http://localhost:5000/static/js/dashboard_socket_fix.js" -Method Head -ErrorAction SilentlyContinue
```

**Expected**: Both should return HTTP 200 (not 404)

### Monitor Socket Connection
```javascript
// In browser console, runs every 5 seconds
setInterval(() => {
  const mgr = window.DashboardSocketManager;
  console.log('Socket connected:', mgr.isConnected());
  console.log('Active charts:', window.ChartResponsivityManager.charts.length);
}, 5000);
```

---

## Rollback Procedure (If Issues)

### Immediate Rollback (< 2 minutes)

```bash
# Restore dashboard.html from backup
cp web/templates/dashboard.html.bak web/templates/dashboard.html

# Restart Flask server
net stop servermonitor
net start servermonitor

# Hard refresh browser
# DevTools → Clear cache → Reload
```

**Expected**: Dashboard returns to pre-deployment state

### Rollback Verification
```javascript
// In console:
typeof window.DashboardSocketManager
// Should return 'undefined' after rollback

typeof window.ChartResponsivityManager
// Should return 'undefined' after rollback
```

---

## Common Issues & Solutions

### Issue: Green dot doesn't appear
**Solution**:
1. Hard refresh (Ctrl+Shift+R)
2. Clear cache in DevTools
3. Check browser console for errors
4. Verify JS file loaded: `document.querySelector('script[src*="socket"]')`

### Issue: Charts not resizing on mobile
**Solution**:
1. Verify CSS file loaded
2. Check DevTools → Network for 404s
3. Rotate device and wait 2-3 seconds
4. Manual test: `window.ChartResponsivityManager.resizeAll()`

### Issue: Metrics not updating
**Solution**:
1. Check Socket status (should be connected)
2. Look at DevTools Network → WS connections
3. Check backend logs for errors
4. Verify metrics endpoint working: `curl http://localhost:5000/api/v2/metrics`

### Issue: CSS not loading
**Solution**:
1. Check server logs for 404 errors
2. Verify file exists: `ls -la web/static/css/dashboard_mobile_fixes.css`
3. Check file permissions: `chmod 644 web/static/css/dashboard_mobile_fixes.css`
4. Restart server to clear any caching

---

## Post-Deployment Monitoring (First 24 Hours)

### Monitor These Metrics
1. **Error rate**: Should remain < 0.1% (no new errors)
2. **Socket.IO connection time**: Should be < 5 seconds
3. **Metrics update frequency**: Should be 5-8 seconds
4. **Page load time**: Should increase < 50ms
5. **Mobile traffic**: Should increase (if mobile users previously avoided)

### Check These Logs
```bash
# Flask logs
tail -f logs/app.log

# Socket.IO logs (if enabled)
grep "socket" logs/app.log

# Error logs
grep "ERROR" logs/app.log
grep "Exception" logs/app.log
```

### User Feedback Channels
- Monitor error reporting system
- Check user support tickets
- Monitor uptime/alerting system

---

## Deployment Completion Checklist

- [ ] Step 1: Verified files exist
- [ ] Step 2: Verification script passed
- [ ] Step 3: Flask server restarted
- [ ] Step 4: Dashboard opens without errors
- [ ] Step 5: Green dot appears (socket connected)
- [ ] Step 6: Metrics update every 5-8 seconds
- [ ] Step 7: Mobile device tested (at least one)
- [ ] Step 8: No 404 errors in DevTools Network tab
- [ ] Step 9: No JavaScript errors in console
- [ ] Step 10: Monitoring setup confirmed

**Deployment Status**: ✅ COMPLETE when all boxes checked

---

## Rollback Triggers

Initiate rollback if ANY of these occur:
- [ ] Dashboard completely broken (won't load)
- [ ] 404 errors for CSS/JS files persisting after restart
- [ ] Socket.IO causes excessive errors (>10 per minute)
- [ ] Page load time increased by >500ms
- [ ] Major functionality broken (charts won't display)
- [ ] Users report widespread issues within 30 minutes

**Rollback Decision**: Based on severity, initiate immediately

---

## Success Criteria

Deployment is successful when:
✅ Green dot appears and stays green  
✅ Metrics update every 5-8 seconds  
✅ Dashboard works on mobile (vertical + horizontal)  
✅ Charts resize smoothly on window resize  
✅ No new errors in browser console  
✅ No 404 errors in Network tab  
✅ Users report positive feedback (if applicable)  

---

## Contact & Escalation

**For deployment support**:
1. Check this guide
2. Review IMPLEMENTATION_COMPLETE.md
3. Review SOCKET_IO_AND_MOBILE_FIXES.md section: "Troubleshooting"
4. Contact DevOps team

**Critical Issues**:
1. Activate incident response
2. Prepare rollback
3. Notify stakeholders

---

## Notes

- **No database changes**: This deployment is pure frontend
- **No backend API changes**: All existing endpoints unchanged
- **Backward compatible**: Works with old and new versions
- **Low risk**: Isolated CSS and JS, no critical dependencies
- **Reversible**: Quick rollback available

---

**Deployment Guide Version**: 1.0  
**Last Updated**: June 1, 2026  
**Status**: Ready for Deployment ✅

For detailed technical documentation, see: **SOCKET_IO_AND_MOBILE_FIXES.md**
