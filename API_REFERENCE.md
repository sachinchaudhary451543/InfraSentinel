"""
COMPLETE API REFERENCE - License Management & Analytics System
All available endpoints with examples and response formats
"""

# ════════════════════════════════════════════════════════════════════════════════════

# ANALYTICS API - /api/v2/analytics

# ════════════════════════════════════════════════════════════════════════════════════

## 1. GET /api/v2/analytics/overview

## Description: Get complete system overview - device/user/server counts and status breakdown

## Authentication: Admin only

## Response:

{
"success": true,
"timestamp": "2026-05-10T15:30:00",
"devices": {
"total": 584,
"active": 432,
"inactive": 128,
"retired": 24,
"active_percentage": 74.14
},
"users": {
"total": 256,
"active": 201,
"terminated": 15,
"onleave": 8,
"active_percentage": 78.52
},
"servers": {
"total": 584,
"online": 512,
"offline": 72
}
}

## 2. GET /api/v2/analytics/devices/activity-timeline

## Description: Get timeline of device activity over last 90 days (10-day intervals)

## Authentication: Admin only

## Response:

{
"success": true,
"timeline": [
{
"period": "2026-02-08 to 2026-02-18",
"active_devices": 45
},
{
"period": "2026-02-18 to 2026-02-28",
"active_devices": 52
},
...
]
}

## 3. GET /api/v2/analytics/employees/device-mapping

## Description: Get mapping of employees to their assigned devices

## Authentication: Admin only

## Response:

{
"success": true,
"total_employees": 156,
"employees": [
{
"id": 1,
"email": "john.doe@company.com",
"name": "John Doe",
"department": "Engineering",
"device_count": 3
},
...
]
}

## 4. GET /api/v2/analytics/employees/device-details?employee_id=1

## Description: Get detailed device list for a specific employee

## Authentication: Admin only

## Response:

{
"success": true,
"employee": {
"id": 1,
"email": "john.doe@company.com",
"name": "John Doe",
"department": "Engineering"
},
"devices": [
{
"id": 42,
"name": "LAPTOP-JD001",
"type": "Windows",
"os": "Windows 11",
"status": "active",
"last_activity": "2026-05-10T14:22:00",
"is_compliant": true
},
...
]
}

## 5. GET /api/v2/analytics/inactivity-report?days=90

## Description: Get report of inactive devices and users

## Authentication: Admin only

## Query Params:

## - days: Inactivity threshold in days (default: 90)

## Response:

{
"success": true,
"threshold_days": 90,
"threshold_date": "2026-02-10T00:00:00",
"devices": {
"count": 128,
"items": [
{
"id": 10,
"name": "OLD-DEVICE-001",
"last_activity": "2026-01-15T09:30:00",
"days_inactive": 116
},
...
]
},
"users": {
"count": 32,
"items": [
{
"id": 5,
"email": "former.employee@company.com",
"name": "Former Employee",
"last_activity": "2025-11-20T14:22:00",
"days_inactive": 172
},
...
]
}
}

# ════════════════════════════════════════════════════════════════════════════════════

# LICENSE MANAGEMENT API - /api/v2/licenses

# ════════════════════════════════════════════════════════════════════════════════════

## 1. GET /api/v2/licenses/overview

## Description: Get complete license overview - totals, breakdown by SKU, utilization

## Authentication: Admin only

## Response:

{
"success": true,
"timestamp": "2026-05-10T15:30:00",
"summary": {
"total_licenses": 500,
"assigned_licenses": 387,
"available_licenses": 113,
"utilization_percentage": 77.4
},
"licenses": [
{
"id": 1,
"sku_id": "ENTERPRISEPACK",
"sku_name": "ENTERPRISEPACK",
"product_name": "Office 365 E3",
"total": 200,
"assigned": 180,
"available": 20,
"utilization": 90.0,
"last_synced": "2026-05-10T02:00:00"
},
{
"id": 2,
"sku_id": "EMSPREMIUM",
"sku_name": "EMSPREMIUM",
"product_name": "Enterprise Mobility + Security E5",
"total": 150,
"assigned": 125,
"available": 25,
"utilization": 83.33,
"last_synced": "2026-05-10T02:00:00"
},
...
]
}

## 2. GET /api/v2/licenses/{license_id}/breakdown

## Description: Get detailed breakdown of a specific license with employee assignments

## Authentication: Admin only

## Response:

{
"success": true,
"license": {
"id": 1,
"sku_id": "ENTERPRISEPACK",
"sku_name": "ENTERPRISEPACK",
"product_name": "Office 365 E3",
"total": 200,
"assigned": 180,
"available": 20
},
"assigned_users": [
{
"user_id": 10,
"email": "user1@company.com",
"name": "User One",
"department": "Sales",
"assigned_at": "2026-01-15T10:30:00",
"disabled_plans": "[]"
},
...
],
"assignment_count": 180
}

## 3. GET /api/v2/licenses/user/{user_id}/assignments

## Description: Get all licenses assigned to a specific user

## Authentication: Admin only

## Response:

{
"success": true,
"user": {
"id": 10,
"email": "user1@company.com",
"name": "User One",
"department": "Sales"
},
"licenses": [
{
"sku_name": "ENTERPRISEPACK",
"product_name": "Office 365 E3",
"assigned_at": "2026-01-15T10:30:00",
"disabled_plans": "[]"
},
{
"sku_name": "EMSPREMIUM",
"product_name": "Enterprise Mobility + Security E5",
"assigned_at": "2026-01-16T09:15:00",
"disabled_plans": "[\"Microsoft Intune\"]"
}
],
"license_count": 2
}

## 4. GET /api/v2/licenses/report/utilization

## Description: Get license utilization report grouped by utilization levels

## Authentication: Admin only

## Response:

{
"success": true,
"timestamp": "2026-05-10T15:30:00",
"summary": {
"high_utilization": 3, // 80%+
"medium_utilization": 5, // 50-79%
"low_utilization": 2 // 0-49%
},
"high_utilization_licenses": [
{
"id": 1,
"product_name": "Office 365 E3",
"total": 200,
"assigned": 180,
"available": 20,
"utilization": 90.0
},
...
],
"medium_utilization_licenses": [
{
"id": 2,
"product_name": "Enterprise Mobility + Security E5",
"total": 150,
"assigned": 105,
"available": 45,
"utilization": 70.0
},
...
],
"low_utilization_licenses": [
{
"id": 5,
"product_name": "Power BI Pro",
"total": 50,
"assigned": 15,
"available": 35,
"utilization": 30.0
},
...
]
}

## 5. GET /api/v2/licenses/sync-status

## Description: Get last sync time and status for licenses

## Authentication: Admin only

## Response:

{
"success": true,
"last_synced": "2026-05-10T02:00:00",
"last_synced_ago": "0:13:30.214192"
}

# ════════════════════════════════════════════════════════════════════════════════════

# STATUS MANAGEMENT API - /api/v2/status

# ════════════════════════════════════════════════════════════════════════════════════

## 1. POST /api/v2/status/azure/device/{device_id}/retire

## Description: Mark a device as permanently retired

## Authentication: Admin only

## Body: {} (empty)

## Response:

{
"success": true,
"message": "Device marked as retired",
"device_id": 10,
"status": "retired"
}

## 2. POST /api/v2/status/azure/device/{device_id}/mark-inactive

## Description: Manually mark a device as inactive

## Authentication: Admin only

## Body: {} (empty)

## Response:

{
"success": true,
"message": "Device marked as inactive",
"device_id": 10
}

## 3. POST /api/v2/status/azure/device/{device_id}/reactivate

## Description: Reactivate a previously inactive device

## Authentication: Admin only

## Body: {} (empty)

## Response:

{
"success": true,
"message": "Device reactivated",
"device_id": 10,
"status": "active"
}

## 4. POST /api/v2/status/azure/user/{user_id}/mark-terminated

## Description: Mark a user as terminated with optional exit date

## Authentication: Admin only

## Body:

{
"left_date": "2026-05-10" // Optional, defaults to today
}

## Response:

{
"success": true,
"message": "User marked as terminated",
"user_id": 5,
"employment_status": "terminated",
"left_date": "2026-05-10"
}

## 5. POST /api/v2/status/azure/user/{user_id}/mark-onleave

## Description: Mark a user as on temporary leave

## Authentication: Admin only

## Body: {} (empty)

## Response:

{
"success": true,
"message": "User marked as on leave",
"user_id": 5,
"employment_status": "onleave"
}

## 6. POST /api/v2/status/azure/user/{user_id}/reactivate

## Description: Reactivate a user from leave or inactive status

## Authentication: Admin only

## Body: {} (empty)

## Response:

{
"success": true,
"message": "User reactivated",
"user_id": 5,
"employment_status": "active"
}

## 7. GET /api/v2/status/devices/inactive-summary

## Description: Get summary of inactive devices

## Authentication: Admin only

## Response:

{
"success": true,
"inactive_devices": 128,
"total_devices": 584,
"percentage": 21.92,
"recent_inactives": [
{
"device_id": 42,
"name": "LAPTOP-OLD-001",
"last_activity": "2026-04-20T10:30:00",
"days_inactive": 20
},
...
]
}

## 8. GET /api/v2/status/users/inactive-summary

## Description: Get summary of inactive/terminated users

## Authentication: Admin only

## Response:

{
"success": true,
"inactive_users": 32,
"terminated_users": 15,
"onleave_users": 8,
"total_users": 256,
"recent_changes": [
{
"user_id": 5,
"email": "former.employee@company.com",
"status": "terminated",
"changed_at": "2026-05-09T14:30:00",
"left_date": "2026-05-09"
},
...
]
}

## 9. POST /api/v2/status/auto-mark-inactive

## Description: Manually trigger automatic inactive detection for entire tenant

## Authentication: Admin only, requires superadmin role

## Body: {} (empty)

## Response:

{
"success": true,
"message": "Auto-detection completed",
"devices_marked_inactive": 12,
"users_marked_inactive": 3,
"users_marked_terminated": 1
}

# ════════════════════════════════════════════════════════════════════════════════════

# ERROR RESPONSES

# ════════════════════════════════════════════════════════════════════════════════════

All endpoints follow standard error response format:

HTTP 401 - Unauthorized:
{
"error": "Login required"
}

HTTP 403 - Forbidden (Admin only):
{
"error": "Admin only"
}

HTTP 404 - Not Found:
{
"success": false,
"error": "License not found"
}

HTTP 500 - Server Error:
{
"success": false,
"error": "Error message describing the problem"
}

# ════════════════════════════════════════════════════════════════════════════════════

# CURL EXAMPLES

# ════════════════════════════════════════════════════════════════════════════════════

## Get License Overview

curl -X GET "http://localhost:5000/api/v2/licenses/overview" \
 -H "Cookie: session=YOUR_SESSION_ID" \
 -H "Accept: application/json"

## Get Device Activity Timeline

curl -X GET "http://localhost:5000/api/v2/analytics/devices/activity-timeline" \
 -H "Cookie: session=YOUR_SESSION_ID" \
 -H "Accept: application/json"

## Get Employee Device Mapping

curl -X GET "http://localhost:5000/api/v2/analytics/employees/device-mapping" \
 -H "Cookie: session=YOUR_SESSION_ID" \
 -H "Accept: application/json"

## Get Inactivity Report (Last 60 days)

curl -X GET "http://localhost:5000/api/v2/analytics/inactivity-report?days=60" \
 -H "Cookie: session=YOUR_SESSION_ID" \
 -H "Accept: application/json"

## Get License Utilization Report

curl -X GET "http://localhost:5000/api/v2/licenses/report/utilization" \
 -H "Cookie: session=YOUR_SESSION_ID" \
 -H "Accept: application/json"

## Mark Device as Retired

curl -X POST "http://localhost:5000/api/v2/status/azure/device/42/retire" \
 -H "Cookie: session=YOUR_SESSION_ID" \
 -H "Content-Type: application/json" \
 -d "{}"

## Mark User as Terminated

curl -X POST "http://localhost:5000/api/v2/status/azure/user/5/mark-terminated" \
 -H "Cookie: session=YOUR_SESSION_ID" \
 -H "Content-Type: application/json" \
 -d "{\"left_date\": \"2026-05-10\"}"

## Get User's Assigned Licenses

curl -X GET "http://localhost:5000/api/v2/licenses/user/10/assignments" \
 -H "Cookie: session=YOUR_SESSION_ID" \
 -H "Accept: application/json"

## Get License Breakdown

curl -X GET "http://localhost:5000/api/v2/licenses/1/breakdown" \
 -H "Cookie: session=YOUR_SESSION_ID" \
 -H "Accept: application/json"

# ════════════════════════════════════════════════════════════════════════════════════

# SCHEDULED AUTOMATIC OPERATIONS

# ════════════════════════════════════════════════════════════════════════════════════

WEEKLY SYNC (Monday 2:00 AM UTC):
POST /api/v2/sync/azure
Automatically:
• Fetches all Azure devices
• Detects activity status (last sign-in < 90 days = active)
• Fetches all Azure users
• Detects employment status
• Syncs all license SKUs and assignments
• Creates device-owner mappings

DAILY INACTIVE DETECTION (Daily 3:00 AM UTC):
POST /api/v2/status/auto-mark-inactive
Automatically:
• Marks devices inactive if no activity > 90 days
• Marks users inactive if no activity > 120 days
• Updates employment status based on Azure account state

# ════════════════════════════════════════════════════════════════════════════════════

# API USAGE SUMMARY

# ════════════════════════════════════════════════════════════════════════════════════

Total Endpoints: 16
• Analytics: 5 endpoints (overview, timelines, mappings, reports)
• Licenses: 5 endpoints (overview, breakdown, assignments, reports, sync status)
• Status Management: 6 endpoints (device/user lifecycle management)

All endpoints require:
• Authentication (Flask-Login session)
• Admin role (superadmin for some endpoints)
• Proper tenant scope (multi-tenant aware)

Response Format: JSON
• success: boolean
• timestamp: ISO 8601 datetime
• data: Specific to endpoint

Pagination: Not yet implemented (future enhancement)
Caching: Real-time, no caching
Rate Limiting: None (future enhancement)
"""
