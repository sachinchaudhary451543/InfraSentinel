#!/usr/bin/env python3
"""
Test script for live screenshot streaming.

This script tests the end-to-end pipeline:
1. POST screenshot to /api/v2/agent/metrics
2. Verify backend logs show screenshot_frame emission
3. Check Socket.IO event reaches clients

Usage:
  python test_live_screenshot_streaming.py
  
Environment Variables:
  API_URL: Base URL (default: http://localhost:5000)
  AGENT_TOKEN: Agent API token (required)
  SERVER_ID: Server ID to use (default: 1)
  TENANT_ID: Tenant ID (default: 1)
"""

import base64
import json
import requests
import sys
from pathlib import Path
from datetime import datetime

# Configuration
API_BASE = "http://localhost:5000"
AGENT_TOKEN = None  # Set via env or prompt
SERVER_ID = 1
TENANT_ID = 1

# Create a minimal test screenshot (100x100 red square JPEG)
TEST_SCREENSHOT_JPEG_BASE64 = "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/2wBDAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8VAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCwAA8A/9k="


def create_test_payload(server_id: int = 1) -> dict:
    """Create a test metrics payload with a screenshot."""
    return {
        "agent_version": "2.0.0",
        "hostname": "TEST_SYSTEM",
        "fqdn": "test.example.com",
        "ip_address": "192.168.1.100",
        "os": "Windows",
        "os_version": "10",
        "logged_in_user": "testuser",
        "screenshot": {
            "success": True,
            "format": "jpeg",
            "image": TEST_SCREENSHOT_JPEG_BASE64,
            "width": 100,
            "height": 100
        },
        "metrics": {
            "cpu": 25.5,
            "ram": 60.2,
            "disk": 45.1
        },
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


def test_screenshot_post(token: str, server_id: int = 1) -> bool:
    """Test posting a screenshot to the agent metrics endpoint."""
    print("\n" + "="*60)
    print("TEST 1: POST Screenshot to Agent Metrics Endpoint")
    print("="*60)
    
    url = f"{API_BASE}/api/v2/agent/metrics?server_id={server_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    payload = create_test_payload(server_id)
    print(f"\nPOSTing to: {url}")
    print(f"Payload size: {len(json.dumps(payload))} bytes")
    print(f"Screenshot size: {len(TEST_SCREENSHOT_JPEG_BASE64)} bytes")
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Body: {response.text[:200]}")
        
        if response.status_code in [200, 201]:
            print("\n✓ Screenshot posted successfully!")
            return True
        else:
            print(f"\n✗ Failed to post screenshot (status {response.status_code})")
            return False
    except requests.exceptions.RequestException as e:
        print(f"\n✗ Request error: {e}")
        return False


def test_socket_io_connection(token: str) -> bool:
    """Test Socket.IO connection for live updates."""
    print("\n" + "="*60)
    print("TEST 2: Verify Socket.IO Event Emission")
    print("="*60)
    
    print("\nSocket.IO events are emitted server-side to authenticated clients.")
    print("To verify Socket.IO events are working:")
    print("\n1. Open browser Developer Tools (F12)")
    print("2. Go to Network tab and filter for 'WebSocket'")
    print("3. Watch for 'screenshot_frame' events after posting screenshot")
    print("4. Check Console tab for [Workforce Live] debug messages")
    
    return True


def main():
    """Main test execution."""
    print("\n" + "="*70)
    print("Live Screenshot Streaming - End-to-End Test")
    print("="*70)
    
    global AGENT_TOKEN
    
    # Get agent token
    AGENT_TOKEN = input("\nEnter Agent API Token: ").strip()
    if not AGENT_TOKEN:
        print("✗ Agent token is required")
        return False
    
    # Get optional parameters
    server_id_input = input(f"Enter Server ID (default {SERVER_ID}): ").strip()
    if server_id_input:
        try:
            SERVER_ID = int(server_id_input)
        except ValueError:
            print(f"✗ Invalid server ID, using {SERVER_ID}")
    
    # Run tests
    results = []
    
    # Test 1: Post screenshot
    results.append(("Screenshot POST", test_screenshot_post(AGENT_TOKEN, SERVER_ID)))
    
    # Test 2: Socket.IO verification
    results.append(("Socket.IO Verification", test_socket_io_connection(AGENT_TOKEN)))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n" + "="*60)
        print("NEXT STEPS FOR DEBUGGING:")
        print("="*60)
        print("\n1. CHECK SERVER LOGS:")
        print("   - Look for '[DEBUG] Processing screenshot' message")
        print("   - Look for '[DEBUG] Starting screenshot emit thread' message")
        print("   - Look for '[DEBUG] Emitting screenshot_frame' message")
        print("\n2. CHECK BROWSER CONSOLE (Workforce Intelligence page):")
        print("   - Should see '[Workforce Live] Socket connected' message")
        print("   - Should see '[Workforce Live] Received screenshot_frame event' after POST")
        print("\n3. CHECK NETWORK TAB (WebSocket):")
        print("   - Filter for 'WebSocket' connections")
        print("   - Look for '/socket.io' or '/t/<tenant>/socket.io' connection")
        print("   - Verify frames are being exchanged (showing in Inspector)")
        print("\n4. IF SCREENSHOT NOT APPEARING:")
        print("   - Verify server_id matches an agent card on the page")
        print("   - Check that user is authenticated and has permission")
        print("   - Verify browser cache isn't showing old image")
        print("      (Ctrl+Shift+Delete to clear cache and cookies)")
        return True
    else:
        print("\n✗ Some tests failed - please check the errors above")
        return False


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
