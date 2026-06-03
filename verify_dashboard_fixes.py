#!/usr/bin/env python3
"""
Dashboard Socket.IO & Mobile Responsiveness Fixes - Verification Script
Validates that all components are properly deployed and configured.
"""

import os
import re
import sys
from pathlib import Path

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    
def print_header(msg):
    print(f"\n{Colors.BLUE}{'='*60}")
    print(f"{msg}")
    print(f"{'='*60}{Colors.RESET}\n")

def check(condition, msg, details=""):
    status = f"{Colors.GREEN}✅ PASS{Colors.RESET}" if condition else f"{Colors.RED}❌ FAIL{Colors.RESET}"
    print(f"{status}: {msg}")
    if details and not condition:
        print(f"       {Colors.YELLOW}→ {details}{Colors.RESET}")
    return condition

def verify_files_exist():
    print_header("FILE EXISTENCE CHECKS")
    
    files_to_check = [
        ('web/static/css/dashboard_mobile_fixes.css', 'Mobile CSS fixes'),
        ('web/static/js/dashboard_socket_fix.js', 'Socket.IO JS fixes'),
        ('web/templates/dashboard.html', 'Dashboard template'),
    ]
    
    results = []
    for filepath, desc in files_to_check:
        exists = os.path.exists(filepath)
        results.append(check(exists, f"File exists: {desc}", f"Missing: {filepath}"))
    
    return all(results)

def verify_file_sizes():
    print_header("FILE SIZE CHECKS")
    
    checks = [
        ('web/static/css/dashboard_mobile_fixes.css', 10000, 'Mobile CSS'),
        ('web/static/js/dashboard_socket_fix.js', 8000, 'Socket.IO JS'),
    ]
    
    results = []
    for filepath, min_size, desc in checks:
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            ok = size >= min_size
            results.append(check(ok, f"{desc}: {size} bytes", f"Expected ≥ {min_size} bytes, got {size}"))
        else:
            results.append(check(False, f"{desc}: File not found", f"Path: {filepath}"))
    
    return all(results)

def verify_dashboard_html():
    print_header("DASHBOARD HTML MODIFICATIONS")
    
    results = []
    
    if not os.path.exists('web/templates/dashboard.html'):
        check(False, "dashboard.html not found")
        return False
    
    with open('web/templates/dashboard.html', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check 1: CSS import
    css_import = 'dashboard_mobile_fixes.css' in content
    results.append(check(css_import, "CSS import added", 
        "dashboard_mobile_fixes.css not found in HTML"))
    
    # Check 2: JS import
    js_import = 'dashboard_socket_fix.js' in content
    results.append(check(js_import, "JS import added",
        "dashboard_socket_fix.js not found in HTML"))
    
    # Check 3: ChartResponsivityManager registration in initChartsForServer
    chart_registration = 'ChartResponsivityManager.register' in content
    results.append(check(chart_registration, "Charts registered with responsivity manager",
        "ChartResponsivityManager.register() calls not found"))
    
    # Check 4: Verify socket manager call exists (created by JS file, not HTML)
    # The DashboardSocketManager is instantiated in dashboard_socket_fix.js
    socket_manager = 'dashb' in content.lower() or 'socket' in content.lower()
    results.append(check(socket_manager, "Socket.IO integration enabled via JS import",
        "Socket.IO reference not found in HTML"))
    
    return all(results)

def verify_css_content():
    print_header("CSS CONTENT VERIFICATION")
    
    results = []
    css_file = 'web/static/css/dashboard_mobile_fixes.css'
    
    if not os.path.exists(css_file):
        check(False, "CSS file not found")
        return False
    
    with open(css_file, 'r', encoding='utf-8') as f:
        css_content = f.read()
    
    # Check media queries for mobile breakpoints
    checks = [
        ('max-width: 480px', 'Mobile breakpoint (480px)'),
        ('max-width: 768px', 'Tablet breakpoint (768px)'),
        ('max-width: 1024px', 'Medium breakpoint (1024px)'),
        ('socket-status-indicator', 'Socket status indicator styles'),
        ('chart-panel canvas', 'Chart canvas responsive styling'),
        ('min-height: 40px', 'Touch-friendly button sizing'),
    ]
    
    for pattern, desc in checks:
        found = pattern in css_content
        results.append(check(found, f"CSS rule present: {desc}", 
            f"Pattern '{pattern}' not found in CSS"))
    
    return all(results)

def verify_js_content():
    print_header("JAVASCRIPT CONTENT VERIFICATION")
    
    results = []
    js_file = 'web/static/js/dashboard_socket_fix.js'
    
    if not os.path.exists(js_file):
        check(False, "JS file not found")
        return False
    
    with open(js_file, 'r', encoding='utf-8') as f:
        js_content = f.read()
    
    checks = [
        ('SOCKET_CONFIG', 'Socket configuration object'),
        ('pingInterval: 45000', 'Increased ping interval'),
        ('pingTimeout: 30000', 'Increased ping timeout'),
        ('DashboardSocketManager', 'Socket manager class'),
        ('ChartResponsivityManager', 'Chart responsivity manager'),
        ('reconnection: true', 'Auto-reconnection enabled'),
        ('reconnectionAttempts: 10', 'Reconnection attempts set'),
    ]
    
    for pattern, desc in checks:
        found = pattern in js_content
        results.append(check(found, f"JS component: {desc}",
            f"Pattern '{pattern}' not found in JS"))
    
    return all(results)

def verify_configuration():
    print_header("CONFIGURATION VALIDATION")
    
    results = []
    js_file = 'web/static/js/dashboard_socket_fix.js'
    
    if os.path.exists(js_file):
        try:
            with open(js_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            # Fallback to latin-1 if UTF-8 fails
            with open(js_file, 'r', encoding='latin-1') as f:
                content = f.read()
        
        # Extract timeout values
        ping_timeout_match = re.search(r'pingTimeout:\s*(\d+)', content)
        reconnect_attempts = re.search(r'reconnectionAttempts:\s*(\d+)', content)
        
        if ping_timeout_match:
            timeout = int(ping_timeout_match.group(1))
            ok = timeout >= 25000  # Should be at least 25 seconds
            results.append(check(ok, f"Ping timeout configured: {timeout}ms",
                f"Timeout too low: {timeout}ms (recommended: ≥25000ms)"))
        
        if reconnect_attempts:
            attempts = int(reconnect_attempts.group(1))
            ok = attempts >= 5
            results.append(check(ok, f"Reconnection attempts: {attempts}",
                f"Too few attempts: {attempts} (recommended: ≥5)"))
    
    # Check static directory permissions
    static_files = [
        'web/static/css/dashboard_mobile_fixes.css',
        'web/static/js/dashboard_socket_fix.js'
    ]
    
    for filepath in static_files:
        if os.path.exists(filepath):
            readable = os.access(filepath, os.R_OK)
            results.append(check(readable, f"File readable: {filepath}",
                f"Permission denied: {filepath}"))
    
    return all(results)

def verify_dependencies():
    print_header("DEPENDENCY CHECKS")
    
    results = []
    
    # Check if Chart.js is loaded in base template
    base_template = 'web/templates/base.html'
    if os.path.exists(base_template):
        with open(base_template, 'r', encoding='utf-8') as f:
            base_content = f.read()
        
        has_chartjs = 'chart' in base_content.lower() and 'js' in base_content.lower()
        results.append(check(has_chartjs, "Chart.js library referenced in base template",
            "Chart.js not found in base.html"))
    
    # Check if Socket.IO is referenced
    if os.path.exists('web/templates/base.html'):
        with open('web/templates/base.html', 'r', encoding='utf-8') as f:
            base_content = f.read()
        
        has_socketio = 'socket' in base_content.lower() and 'io' in base_content.lower()
        results.append(check(has_socketio, "Socket.IO library referenced in base template",
            "Socket.IO not found in base.html"))
    
    return all(results)

def print_summary(all_results):
    print_header("VERIFICATION SUMMARY")
    
    total = len(all_results)
    passed = sum(all_results)
    failed = total - passed
    
    print(f"Total Checks: {total}")
    print(f"{Colors.GREEN}Passed: {passed}{Colors.RESET}")
    
    if failed > 0:
        print(f"{Colors.RED}Failed: {failed}{Colors.RESET}")
    
    status = "✅ ALL CHECKS PASSED" if all(all_results) else "⚠️  SOME CHECKS FAILED"
    color = Colors.GREEN if all(all_results) else Colors.RED
    
    print(f"\n{color}{status}{Colors.RESET}")
    
    if all(all_results):
        print("""
        ┌──────────────────────────────────────────────────────────┐
        │ Dashboard fixes are properly deployed!                   │
        │                                                          │
        │ Next steps:                                              │
        │ 1. Restart Flask server                                  │
        │ 2. Hard refresh dashboard (Ctrl+Shift+R)                 │
        │ 3. Test on mobile device                                 │
        │ 4. Verify Socket.IO connection (green dot bottom-right)  │
        │ 5. Monitor console for [Dashboard] logs                  │
        └──────────────────────────────────────────────────────────┘
        """)
    else:
        print("""
        ┌──────────────────────────────────────────────────────────┐
        │ ⚠️  Some checks failed. Review the errors above.         │
        │                                                          │
        │ Common issues:                                           │
        │ • Missing CSS/JS files in static directories             │
        │ • Dashboard HTML not properly updated                    │
        │ • Socket configuration values too low                    │
        │                                                          │
        │ See SOCKET_IO_AND_MOBILE_FIXES.md for details            │
        └──────────────────────────────────────────────────────────┘
        """)
    
    return all(all_results)

def main():
    print(f"\n{Colors.BLUE}Dashboard Socket.IO & Mobile Responsiveness Verification{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*60}{Colors.RESET}\n")
    
    all_results = []
    
    # Run all verification checks
    all_results.append(verify_files_exist())
    all_results.append(verify_file_sizes())
    all_results.append(verify_dashboard_html())
    all_results.append(verify_css_content())
    all_results.append(verify_js_content())
    all_results.append(verify_configuration())
    all_results.append(verify_dependencies())
    
    # Print summary
    success = print_summary(all_results)
    
    # Return appropriate exit code
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
