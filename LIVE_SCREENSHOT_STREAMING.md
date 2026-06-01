# Live Screenshot Streaming Implementation

**Status: ✅ Complete - Ready for Testing**

## Overview

Live screenshot streaming enables real-time display of agent screenshots on the Workforce Intelligence dashboard. When an agent posts a screenshot, it's immediately emitted to connected clients via Socket.IO, updating the card preview without page refresh.

## Architecture

```
Agent System
    ↓ POST with base64 screenshot
Backend /api/v2/agent/metrics
    ↓ Save to disk + DB
    ↓ Emit Socket.IO event to tenant room
Socket.IO Server (Flask-SocketIO)
    ↓ Broadcast to authenticated clients in tenant room
Browser Client
    ↓ Receive screenshot_frame event
    ↓ Update agent card image
Workforce Intelligence Dashboard
```

## Components

### 1. Backend - Flask-SocketIO Server Setup
**Files:** `web/app.py`

- **Socket.IO Initialization** (lines 229-251)
  - Configured with `async_mode='gevent'` for production compatibility
  - `cors_allowed_origins: "*"` for cross-origin connections
  - Optional Redis message queue for multi-worker deployments
  
- **Tenant Room Joining** (lines 604-611)
  - `@socketio.on('join')` handler joins authenticated users to `room=str(current_user.tenant_id)`
  - Enables room-based event distribution (only users in the same tenant receive events)

- **Middleware** (lines 207-221)
  - `TenantPathPrefixMiddleware` strips `/t/<tenant>` from request paths
  - Allows Socket.IO to work with tenant-aware routing

### 2. Backend - Screenshot Ingestion & Emission
**Files:** `web/routes/api.py`

**Agent Metrics Endpoint** (lines 1030-1098)
```python
POST /api/v2/agent/metrics
{
    "screenshot": {
        "success": true,
        "format": "jpeg",
        "image": "<base64-jpeg>",
        "width": 1920,
        "height": 1080
    },
    "metrics": { "cpu": 25.5, "ram": 60.2, "disk": 45.1 },
    ...
}
```

**Processing Steps:**
1. Receive base64 screenshot image from agent
2. Decode and save to `/data/screenshots/screenshot_<server_id>_<hostname>_<timestamp>.jpg`
3. Create Screenshot DB row with `local_file_path` and `filename`
4. **Emit Socket.IO event** to tenant room with payload:
   ```python
   {
       'server_id': server.id,
       'timestamp': '2024-01-15T14:30:45Z',
       'image_b64': '<base64-jpeg>',
       'screenshot_id': null
   }
   ```

**Debug Logging:**
- `[DEBUG] Processing screenshot from server X: success=true, image_len=YYYYYYY`
- `[DEBUG] Starting screenshot emit thread for server X to tenant Y`
- `[DEBUG] Emitting screenshot_frame to room=Y for server_id=X, b64_size=YYYYYYY bytes`
- `[DEBUG] Screenshot_frame emitted successfully for server X`

### 3. Backend - Workforce Dashboard Data Provider
**Files:** `web/routes/analytics_api.py`

**Workforce Dashboard Endpoint** (lines 30-160)
```python
GET /t/<tenant>/workforce_intelligence
```

**Data Provided:**
```python
{
    'total_agents': 5,
    'active_agents': 3,
    'idle_agents': 1,
    'offline_agents': 1,
    'screenshot_enabled_count': 4,
    'active_screens': 2,
    'live_agents': [
        {
            'server_id': 1,
            'name': 'IPF_SACHIN',
            'device': 'SACHIN-LAPTOP',
            'device_ip': '192.168.1.100',
            'server_status': 'ONLINE',
            'server_last_seen': '2024-01-15T14:30:45',
            'active_str': '4h 32m',
            'idle_str': '15m',
            'productive_str': '72%',
            'screenshot_enabled': True,
            'screenshot_thumb': '/api/screenshot/123?size=thumb'  # Initial thumbnail or None
        },
        ...
    ]
}
```

**Key Features:**
- Only includes servers with `agent_installed=True`
- Filters employees to only those linked via `EmployeeDeviceAssignment`
- Sets `screenshot_thumb` to `/api/screenshot/<id>?size=thumb` for initial static thumbnail
- Live updates via Socket.IO events replace the static thumbnail with base64 frames

### 4. Frontend - Global Socket.IO Script Loading
**Files:** `web/templates/base.html` (lines 1055-1073)

```javascript
<script>
(function() {
    const pathname = window.location.pathname || '';
    const parts = pathname.split('/').filter(Boolean);
    let socketPath = '/socket.io/socket.io.js';
    
    // Handle tenant prefix like /t/<slug>
    if (parts.length >= 2 && parts[0] === 't') {
        socketPath = `/${parts[0]}/${parts[1]}/socket.io/socket.io.js`;
    }
    
    const script = document.createElement('script');
    script.src = socketPath;
    script.onerror = function() {
        console.warn('Socket.IO client failed to load from', socketPath);
    };
    script.onload = function() {
        console.log('[Base] Socket.IO client loaded from', socketPath);
    };
    document.head.appendChild(script);
})();
</script>
```

**Features:**
- Dynamically detects tenant-aware paths from `window.location.pathname`
- Loads Flask-SocketIO client from server endpoint (not CDN) for compatibility
- Includes error handling for failed loads

### 5. Frontend - Workforce Intelligence Socket.IO Client
**Files:** `web/templates/workforce_dashboard.html` (lines 161-260)

**Socket Initialization:**
```javascript
// After base.html loads socket.io.js globally
function initSocketConnection() {
    if (typeof io !== 'function') {
        setTimeout(initSocketConnection, 500);
        return;
    }
    
    const socketPath = window.location.pathname.includes('/t/')
        ? `/${parts[0]}/${parts[1]}/socket.io`
        : '/socket.io';
    
    const socket = io({ path: socketPath, reconnection: true });
    
    socket.on('connect', () => {
        console.log('[Workforce Live] Socket connected');
        socket.emit('join', {});  // Join tenant room
    });
    
    socket.on('screenshot_frame', (data) => {
        // Update card image with base64 frame
    });
}
```

**Event Listener for Live Screenshots:**
```javascript
socket.on('screenshot_frame', function(data) {
    // data = {
    //   server_id: 1,
    //   timestamp: '2024-01-15T14:30:45Z',
    //   image_b64: '<base64-jpeg>',
    //   screenshot_id: null
    // }
    
    // Find card by server_id
    const cards = document.querySelectorAll(`.agent-card[data-server-id="${data.server_id}"]`);
    
    // Update image with base64 data URI
    cards.forEach(card => {
        const img = card.querySelector('.live-preview-img');
        if (img) {
            img.src = `data:image/jpeg;base64,${data.image_b64}`;
            img.classList.add('live-updated');
        }
    });
});
```

**Debug Logging:**
- `[Workforce Live] Socket connected at: /t/tenant1/socket.io`
- `[Workforce Live] Emitted join event to tenant room`
- `[Workforce Live] Received screenshot_frame event: {server_id: 1, timestamp: ...}`
- `[Workforce Live] Updated 1/1 card image(s) for server 1`

### 6. Frontend - Agent Card Markup
**Files:** `web/templates/workforce_dashboard.html` (lines 89-140)

```html
<div class="agent-card" data-server-id="{{ agent.server_id }}">
    <div class="relative h-40 bg-slate-950/5 overflow-hidden">
        <img 
            src="{{ agent.screenshot_thumb or 'data:image/svg+xml,...' }}"
            alt="Live preview for {{ agent.name }}"
            class="w-full h-full object-cover live-preview-img"
        >
        <!-- Placeholder shown when no screenshot available -->
        {% if not agent.screenshot_thumb %}
        <div class="absolute inset-0 flex flex-col items-center justify-center ...">
            <i class="fa-solid fa-monitor-waveform text-3xl mb-3"></i>
            No recent screenshot available
        </div>
        {% endif %}
    </div>
    <!-- Card details: name, device, status, etc. -->
</div>
```

**Key HTML Attributes:**
- `class="agent-card"` - CSS selector for finding all cards
- `data-server-id="{{ agent.server_id }}"` - Identifies which server this card represents
- `class="live-preview-img"` - Image element that gets updated with base64 frames

## Data Flow - Complete Pipeline

### 1. Agent Posts Screenshot
```
Agent Process
├─ Capture screenshot (JPEG)
├─ Encode to base64
└─ POST /api/v2/agent/metrics
    {
        "server_id": 1,
        "hostname": "IPF_SACHIN",
        "screenshot": {
            "success": true,
            "format": "jpeg",
            "image": "yJ/4AAQSkZJRgAB...=",
            "width": 1920,
            "height": 1080
        },
        "metrics": {"cpu": 25.5, ...}
    }
```

### 2. Backend Receives & Processes
```
Flask Endpoint /api/v2/agent/metrics
├─ Validate agent credentials
├─ Load Server from DB (server_id, tenant_id)
├─ Save base64 screenshot
│  ├─ Decode from base64
│  ├─ Write to /data/screenshots/screenshot_1_IPF_SACHIN_20240115_143045.jpg
│  └─ Create Screenshot DB row
├─ Spawn background thread
└─ Emit Socket.IO event
    {
        'server_id': 1,
        'timestamp': '2024-01-15T14:30:45Z',
        'image_b64': 'yJ/4AAQSkZJRgAB...=',
        'screenshot_id': null
    }
```

### 3. Socket.IO Broadcasts to Clients
```
Socket.IO Server
├─ Receive screenshot_frame event from agent_metrics
├─ Emit to room=str(tenant_id)
│  └─ Only authenticated users in this tenant receive
└─ All connected clients in room get event
    {
        'server_id': 1,
        'timestamp': '2024-01-15T14:30:45Z',
        'image_b64': 'yJ/4AAQSkZJRgAB...=',
        'screenshot_id': null
    }
```

### 4. Browser Client Updates UI
```
Workforce Intelligence Page
├─ Socket listens for 'screenshot_frame' events
├─ Find card with data-server-id="1"
├─ Get <img class="live-preview-img">
├─ Set src="data:image/jpeg;base64,yJ/4AAQSkZJRgAB...="
└─ Image renders immediately (no HTTP request needed)
```

## Testing & Verification

### Test 1: Manual Screenshot POST
```bash
python test_live_screenshot_streaming.py
```

Enter agent API token and server ID when prompted. Script will:
- POST screenshot to `/api/v2/agent/metrics`
- Verify successful response
- Provide debugging instructions

### Test 2: Browser Network Inspection
1. Open Workforce Intelligence page
2. Open DevTools (F12) → Network tab
3. Filter for "WebSocket" or "socket.io"
4. Watch for WebSocket connection to `/socket.io` or `/t/<tenant>/socket.io`
5. Look for `screenshot_frame` frames being exchanged

### Test 3: Browser Console Inspection
1. Open DevTools (F12) → Console tab
2. Look for `[Workforce Live]` log messages:
   - "Socket connected at: ..."
   - "Received screenshot_frame event: ..."
   - "Updated X/Y card image(s) for server Z"

### Test 4: Server Log Inspection
Watch application logs for:
```
[DEBUG] Processing screenshot from server 1 (IPF_SACHIN): success=true, image_len=45678
[DEBUG] Starting screenshot emit thread for server 1 to tenant tenant1
[DEBUG] Emitting screenshot_frame to room=1 for server_id=1, b64_size=45678 bytes
[DEBUG] Screenshot_frame emitted successfully for server 1
```

## Configuration

### Environment Variables
- `REDIS_URL`: Optional Redis URL for message queue in multi-worker deployments
- `SOCKETIO_MESSAGE_QUEUE`: Automatically set from REDIS_URL

### Flask-SocketIO Settings (web/app.py)
- `async_mode`: `'gevent'` (for production Gunicorn+Gevent)
- `ping_timeout`: `60` seconds
- `ping_interval`: `25` seconds
- `cors_allowed_origins`: `"*"`

### Screenshot Storage
- Path: `/data/screenshots/screenshot_<server_id>_<hostname>_<timestamp>.<ext>`
- Size limit: No hard limit (depends on server storage)
- Retention: Indefinite (old files should be cleaned up manually or with cron job)

## Common Issues & Troubleshooting

### Issue: Socket.IO 400 Error
**Symptom:** Browser console shows "GET socket.io/socket.io.js 400 (Bad Request)"

**Solution:** Base.html now dynamically detects tenant prefix and loads from correct path
- Fixed by: Tenant-aware path detection in base.html script

### Issue: Screenshot Frame Not Appearing on Card
**Symptom:** Cards show "Live preview pending" placeholder, no updates

**Debugging Steps:**
1. Check server logs for `[DEBUG]` messages confirming screenshot receipt
2. Check browser console for `[Workforce Live]` messages
3. Verify `server_id` in test matches card's `data-server-id`
4. Clear browser cache (Ctrl+Shift+Delete)
5. Verify user is authenticated in same tenant as server

### Issue: Image Not Updating But Socket Connected
**Symptom:** Socket.IO connects successfully but images don't change

**Debugging Steps:**
1. Check browser DevTools Network tab for WebSocket frames with `screenshot_frame` events
2. Verify card has `data-server-id` attribute matching `server_id` in event
3. Check img element has `class="live-preview-img"`
4. Verify base64 data is valid (not truncated or corrupted)

### Issue: "Cannot read properties of undefined" in dashboard.js
**Symptom:** Dashboard crashes with TypeError about accessing array properties

**Solution:** Fixed by adding defensive null checks in handleMetricsUpdate()
- See: `web/templates/dashboard.html` lines 2783-2850

## Performance Considerations

### Base64 Image Transmission
- **Pros:** No additional HTTP requests, immediate display
- **Cons:** Larger payload, embedded in every event
- **Size:** Typical 100KB-300KB base64 per screenshot
- **Frequency:** Agent typically sends 1 screenshot per 10 minutes (configurable)

### Memory Usage
- Base64 frames are NOT persisted in memory (only transmitted)
- JavaScript data URIs are garbage collected when image is updated
- No memory leak with continuous updates

### Network Bandwidth
- Single screenshot: ~100-300KB base64
- Multi-tenant: Events only go to users in tenant room
- Optimized: Gevent async mode handles many concurrent connections

## Future Enhancements

1. **Compression**: Compress base64 before transmission (e.g., gzip)
2. **Throttling**: Limit screenshot frequency per agent to reduce bandwidth
3. **Thumbnails**: Generate smaller thumbnails for card preview
4. **Archive**: Move old screenshots to cloud storage (AWS S3, Azure Blob)
5. **History**: Display screenshot timeline/carousel on card
6. **Analytics**: Track screenshot update frequency and latency
7. **Caching**: Implement client-side cache with versioning
8. **CDN**: Serve static screenshots through CDN after saving

## Files Modified

### Backend
- ✅ `web/app.py` - Socket.IO initialization and join handler
- ✅ `web/routes/api.py` - Screenshot emission in agent_metrics()
- ✅ `web/routes/analytics_api.py` - Workforce dashboard data provider

### Frontend
- ✅ `web/templates/base.html` - Global socket.io.js loading
- ✅ `web/templates/workforce_dashboard.html` - Live screenshot listener
- ✅ `web/templates/dashboard.html` - Fixed metrics update crash

### Testing
- ✅ `test_live_screenshot_streaming.py` - End-to-end test script

## Deployment Checklist

- [ ] Review all code changes
- [ ] Run `test_live_screenshot_streaming.py` on staging
- [ ] Test with real agent in non-production
- [ ] Monitor server logs for `[DEBUG]` messages
- [ ] Verify Socket.IO events appear in browser Network tab
- [ ] Check images update on agent screenshots
- [ ] Clear browser cache on first load
- [ ] Test with multiple concurrent users
- [ ] Verify tenant isolation (events only reach correct tenant users)
- [ ] Monitor memory usage and connection count
- [ ] Set up log monitoring for `[DEBUG]` messages

## Contact & Support

For issues or questions about live screenshot streaming:
1. Check server logs for `[DEBUG]` messages
2. Check browser console for `[Workforce Live]` messages
3. Run `test_live_screenshot_streaming.py` for diagnostics
4. Review this documentation for common issues
