import time
import requests
import psutil
import platform
import socket
import logging
import os
import json
import base64
import io
from pathlib import Path
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load configuration from environment or config file
def load_config():
    """Load configuration from environment variables or config file"""
    # Try to load from config file in multiple locations (service-friendly)
    config_paths = [
        Path('agent_config.json'),  # Current directory
        Path(os.path.dirname(os.path.abspath(__file__))) / 'agent_config.json',  # Script directory
        Path('C:\\Program Files\\InfraSentinel\\Agent\\agent_config.json'),  # Windows Service directory
    ]
    
    for config_path in config_paths:
        if config_path.exists():
            try:
                with open(config_path) as f:
                    config = json.load(f)
                    logger.info(f"Loaded config from: {config_path}")
                    return config.get('AGENT_KEY', ''), config.get('SERVER_URL', ''), config.get('INTERVAL', 30)
            except Exception as e:
                logger.warning(f"Failed to load config file from {config_path}: {e}")
    
    # Fall back to environment variables
    agent_key = os.getenv('AGENT_KEY', os.getenv('SERVER_MONITOR_AGENT_KEY', 'demo_mode_key'))
    server_url = os.getenv('SERVER_URL', os.getenv('SERVER_MONITOR_URL', 'http://localhost:8080'))
    interval = int(os.getenv('AGENT_INTERVAL', os.getenv('SERVER_MONITOR_INTERVAL', 30)))
    
    logger.info(f"Using environment variables or defaults")
    return agent_key, server_url, interval

AGENT_KEY, SERVER_URL, INTERVAL = load_config()

if not AGENT_KEY or AGENT_KEY == 'demo_mode_key':
    logger.warning("⚠️  WARNING: Using demo_mode_key. Set AGENT_KEY env variable for production.")
if SERVER_URL == 'http://localhost:8080':
    logger.info("Connecting to local server. Set SERVER_URL env variable to connect to production.")

# Screenshot state
ENABLE_SCREENSHOTS = False
SCREENSHOT_INTERVAL = 300  # Default 5 minutes
last_screenshot_time = 0

def capture_screenshot():
    """Capture system screenshot and encode as base64"""
    try:
        if platform.system() == 'Windows':
            from PIL import ImageGrab
            screenshot = ImageGrab.grab()
            img_byte_arr = io.BytesIO()
            screenshot.save(img_byte_arr, format='JPEG', quality=60)
            img_byte_arr.seek(0)
            base64_str = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
            return {
                "success": True,
                "image": base64_str,
                "format": "jpeg",
                "timestamp": datetime.now(timezone.utc).isoformat() + 'Z'
            }
    except Exception as e:
        logger.error(f"Screenshot capture failed: {e}")
    return {"success": False, "error": "Capture failed"}

def get_idle_time():
    """Return system idle time in seconds"""
    try:
        if platform.system() == 'Windows':
            from ctypes import Structure, windll, c_uint, sizeof, byref
            class LASTINPUTINFO(Structure):
                _fields_ = [
                    ("cbSize", c_uint),
                    ("dwTime", c_uint)
                ]
            
            lastInputInfo = LASTINPUTINFO()
            lastInputInfo.cbSize = sizeof(lastInputInfo)
            if windll.user32.GetLastInputInfo(byref(lastInputInfo)):
                millis = windll.kernel32.GetTickCount() - lastInputInfo.dwTime
                return millis / 1000.0
            return 0
        else:
            return 0
    except Exception as e:
        logger.error(f"Failed to get idle time: {e}")
        return 0

def get_system_metrics():
    """Collect system metrics using psutil"""
    hostname = socket.gethostname()
    os_info = f"{platform.system()} {platform.release()}"
    
    # Net IP
    try:
        ip = socket.gethostbyname(hostname)
    except:
        ip = "127.0.0.1"

    # Logged-in User (for employee asset detection)
    logged_in_user = None
    try:
        import getpass
        username = getpass.getuser()
        # Uncomment next line to format as email:
        # logged_in_user = f"{username}@company.com"
        logged_in_user = username
    except Exception as e:
        logging.warning(f"Failed to get user info: {e}")

    # CPU
    cpu_percent = psutil.cpu_percent(interval=1)
    
    # RAM
    mem = psutil.virtual_memory()
    ram_percent = mem.percent
    total_ram_gb = round(mem.total / (1024**3), 2)
    used_ram_gb = round(mem.used / (1024**3), 2)
    
    # Disk (Assuming root or C: depending on OS)
    try:
        disk = psutil.disk_usage('/')
    except:
        disk = psutil.disk_usage('C:\\')
        
    disk_percent = disk.percent
    total_disk_gb = round(disk.total / (1024**3), 2)
    used_disk_gb = round(disk.used / (1024**3), 2)

    # Get active window info for productivity tracking
    active_app, window_title = get_active_window_info()
    idle_seconds = get_idle_time()

    return {
        "agent_key": AGENT_KEY,
        "hostname": hostname,
        "os_info": os_info,
        "ip": ip,
        "logged_in_user": logged_in_user,
        "idle_time_seconds": idle_seconds,
        "active_app": active_app,
        "window_title": window_title,
        "activity": {
            "app": active_app,
            "window_title": window_title,
            "idle_seconds": idle_seconds
        },
        "metrics": {
            "cpu_percent": cpu_percent,
            "ram_percent": ram_percent,
            "total_ram_gb": total_ram_gb,
            "used_ram_gb": used_ram_gb,
            "disk_percent": disk_percent,
            "total_disk_gb": total_disk_gb,
            "used_disk_gb": used_disk_gb
        }
    }

import subprocess


def get_active_window_info():
    """Get the currently active window title and application name"""
    active_app = ''
    window_title = ''
    try:
        if platform.system() == 'Windows':
            from ctypes import windll, create_unicode_buffer, c_int
            hwnd = windll.user32.GetForegroundWindow()
            length = windll.user32.GetWindowTextLengthW(hwnd)
            buf = create_unicode_buffer(length + 1)
            windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            window_title = buf.value or ''

            # Get process name from window handle
            try:
                from ctypes import wintypes, byref
                pid = wintypes.DWORD()
                windll.user32.GetWindowThreadProcessId(hwnd, byref(pid))
                proc = psutil.Process(pid.value)
                active_app = proc.name().replace('.exe', '')
            except Exception:
                # Extract app name from window title as fallback
                if ' - ' in window_title:
                    active_app = window_title.rsplit(' - ', 1)[-1].strip()
    except Exception as e:
        logger.debug(f"Failed to get active window info: {e}")
    return active_app, window_title


def fetch_and_execute_commands():
    """Poll for commands and execute them"""
    hostname = socket.gethostname()
    headers = {
        'X-Agent-Key': AGENT_KEY,
        'X-Hostname': hostname
    }
    
    try:
        resp = requests.get(f"{SERVER_URL}/api/v2/agent/commands", headers=headers, timeout=10)
        if resp.status_code == 200:
            commands = resp.json()
            for cmd in commands:
                command_str = cmd['command']
                params_raw = cmd.get('parameters', '') or ''
                
                # Handle legacy 'Execute-PowerShell' wrapper format
                if command_str == 'Execute-PowerShell' and params_raw:
                    try:
                        params_obj = json.loads(params_raw)
                        if isinstance(params_obj, dict) and 'script' in params_obj:
                            command_str = params_obj['script']
                        else:
                            command_str += ' ' + params_raw
                    except (json.JSONDecodeError, TypeError):
                        command_str += ' ' + params_raw
                elif params_raw:
                    # For other commands, try to parse JSON params
                    try:
                        params_obj = json.loads(params_raw)
                        if isinstance(params_obj, dict) and 'script' in params_obj:
                            command_str = params_obj['script']
                        elif isinstance(params_obj, str):
                            command_str += ' ' + params_obj
                        else:
                            command_str += ' ' + params_raw
                    except (json.JSONDecodeError, TypeError):
                        command_str += ' ' + params_raw
                    
                logging.info(f"Executing command: {command_str}")
                
                try:
                    # using powershell as default for windows, fallback to shell
                    if platform.system() == "Windows":
                        result = subprocess.run(["powershell", "-Command", command_str], capture_output=True, text=True, timeout=120)
                    else:
                        result = subprocess.run(command_str, shell=True, capture_output=True, text=True, timeout=120)
                        
                    output = (result.stdout or '') + (result.stderr or '')
                    status = 'completed' if result.returncode == 0 else 'failed'
                except subprocess.TimeoutExpired:
                    output = 'Command timed out after 120 seconds'
                    status = 'failed'
                except Exception as e:
                    output = str(e)
                    status = 'failed'
                    
                # Post result
                payload = {
                    'command_id': cmd['command_id'],
                    'output': output,
                    'status': status
                }
                try:
                    resp = requests.post(f"{SERVER_URL}/api/v2/agent/commands/result", headers=headers, json=payload, timeout=10)
                    if resp.status_code == 200:
                        logging.info(f"Command result posted successfully. Command ID: {cmd['command_id']}")
                    else:
                        logging.error(f"Failed to post command result. Status: {resp.status_code} | Response: {resp.text}")
                except Exception as e:
                    logging.error(f"Failed to post command result: {e}")
    except Exception as e:
        logging.error(f"Error fetching commands: {e}")

def main():
    logger.info(f"Starting ServerMonitor Enterprise Agent. Hostname: {socket.gethostname()}")
    logger.info(f"Server URL: {SERVER_URL}")
    logger.info(f"Agent Key: {AGENT_KEY[:10]}..." if len(AGENT_KEY) > 10 else f"Agent Key: {AGENT_KEY}")
    
    global ENABLE_SCREENSHOTS, SCREENSHOT_INTERVAL, last_screenshot_time
    
    while True:
        try:
            payload = get_system_metrics()
            # Send to /api/metrics with api_key instead of agent_key for consistency
            payload['api_key'] = payload.pop('agent_key', AGENT_KEY)
            
            # Screenshot capture logic
            if ENABLE_SCREENSHOTS and (time.time() - last_screenshot_time >= SCREENSHOT_INTERVAL):
                logger.info("📸 Capturing screenshot...")
                ss_data = capture_screenshot()
                if ss_data.get('success'):
                    payload['screenshot'] = ss_data
                    last_screenshot_time = time.time()
            
            resp = requests.post(f"{SERVER_URL}/api/v2/agent/metrics", json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info(f"✓ Metrics sent. CPU: {payload['metrics']['cpu_percent']}% | RAM: {payload['metrics']['ram_percent']}%")
                
                # Update screenshot config from server
                try:
                    resp_data = resp.json()
                    if 'screenshot_enabled' in resp_data:
                        ENABLE_SCREENSHOTS = bool(resp_data['screenshot_enabled'])
                    if 'screenshot_interval_minutes' in resp_data:
                        SCREENSHOT_INTERVAL = int(resp_data['screenshot_interval_minutes']) * 60
                except:
                    pass
            else:
                logger.error(f"✗ Failed to push metrics. Status: {resp.status_code} | Response: {resp.text[:200]}")
        except requests.exceptions.ConnectionError:
            logger.error(f"✗ Connection error: Cannot reach {SERVER_URL}. Check SERVER_URL setting.")
        except requests.exceptions.Timeout:
            logger.error(f"✗ Timeout connecting to {SERVER_URL}")
        except Exception as e:
            logger.error(f"✗ Agent error: {e}")
            
        # Poll for commands
        fetch_and_execute_commands()
            
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()

