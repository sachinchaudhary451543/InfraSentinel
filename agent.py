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
        Path('C:\\Program Files\\ServerMonitor\\Agent\\agent_config.json'),  # Windows Service directory
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
    server_url = os.getenv('SERVER_URL', os.getenv('SERVER_MONITOR_URL', 'http://localhost:5000'))
    interval = int(os.getenv('AGENT_INTERVAL', os.getenv('SERVER_MONITOR_INTERVAL', 30)))
    
    logger.info(f"Using environment variables or defaults")
    return agent_key, server_url, interval

AGENT_KEY, SERVER_URL, INTERVAL = load_config()

if not AGENT_KEY or AGENT_KEY == 'demo_mode_key':
    logger.warning("⚠️  WARNING: Using demo_mode_key. Set AGENT_KEY env variable for production.")
if SERVER_URL == 'http://localhost:5000':
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


def get_top_processes(limit=5):
    """Return the top user-visible processes by CPU and memory for load diagnosis."""
    processes = []
    try:
        for proc in psutil.process_iter(['pid', 'name', 'username', 'memory_percent']):
            try:
                name = (proc.info.get('name') or '').strip()
                if not name or name.lower() in {'system idle process', 'system', 'registry'}:
                    continue
                cpu = proc.cpu_percent(interval=0.02)
                memory = float(proc.info.get('memory_percent') or 0)
                processes.append({
                    'pid': int(proc.info.get('pid') or 0),
                    'name': name[:120],
                    'cpu_percent': round(max(0, cpu), 1),
                    'memory_percent': round(max(0, memory), 1),
                    'user': (proc.info.get('username') or '').split('\\')[-1][:80],
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, ValueError):
                continue
        processes.sort(key=lambda item: (item['cpu_percent'], item['memory_percent']), reverse=True)
    except Exception as exc:
        logger.debug(f"Process load snapshot unavailable: {exc}")
    return processes[:max(1, min(int(limit), 10))]


def get_office_user_id(local_username: str) -> str:
    """Return the signed-in Windows UPN (office email) when Windows provides it.

    The local Windows account remains the safe fallback for workgroup or
    non-Entra devices, where a UPN is not available.
    """
    if platform.system() != 'Windows':
        return local_username
    try:
        result = subprocess.run(
            ['whoami', '/upn'], capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        upn = (result.stdout or '').strip()
        if result.returncode == 0 and '@' in upn and '\n' not in upn:
            return upn
    except Exception as exc:
        logger.debug(f"Office UPN lookup unavailable: {exc}")
    return local_username

def get_system_metrics():
    """Collect system metrics using psutil"""
    import time
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
        
        # If running as SYSTEM (service mode), try to detect actual logged-in user from running processes
        if username.upper() in ['SYSTEM', 'NT AUTHORITY', 'NETWORK SERVICE', 'LOCAL SERVICE']:
            try:
                if platform.system() == 'Windows':
                    logged_in_user = None
                    # Check Windows process ownership to find actual user
                    import ctypes
                    for proc in psutil.process_iter(['username', 'name']):
                        try:
                            user = proc.info['username']
                            proc_name = proc.info['name'].lower()
                            # Look for user processes (not system processes)
                            if user and user not in ['SYSTEM', 'NT AUTHORITY\\SYSTEM'] and 'system' not in proc_name:
                                logged_in_user = user.split('\\')[-1] if '\\' in user else user
                                break
                        except:
                            pass
            except:
                pass
        
        # If still no user detected, use the system getpass user
        if not logged_in_user:
            logged_in_user = username
        office_user_id = get_office_user_id(logged_in_user)
    except Exception as e:
        logging.warning(f"Failed to get user info: {e}")
        logged_in_user = logged_in_user or ''
        office_user_id = logged_in_user

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
    top_processes = get_top_processes()
    
    # Get installed software (cache for 5 minutes to avoid performance impact)
    installed_software = []
    if not hasattr(get_system_metrics, 'last_software_refresh'):
        get_system_metrics.last_software_refresh = 0
    
    current_time = time.time()
    if current_time - get_system_metrics.last_software_refresh >= 300:  # 5 minutes
        try:
            installed_software = get_installed_software()
            get_system_metrics.last_software_refresh = current_time
        except Exception as e:
            logger.warning(f"Failed to get installed software: {e}")

    return {
        "agent_key": AGENT_KEY,
        "hostname": hostname,
        "os_info": os_info,
        "ip": ip,
        "logged_in_user": logged_in_user,
        "office_user_id": office_user_id,
        "local_username": logged_in_user,
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
        },
        "details": {
            "installed_software": installed_software,
            "top_processes": top_processes,
        }
    }

import subprocess


def get_active_window_info():
    """Get the currently active window title and application name
    
    Works in both user mode (interactive session) and service mode (Session 0).
    In service mode, returns the most actively used application instead.
    """
    active_app = ''
    window_title = ''
    try:
        if platform.system() == 'Windows':
            from ctypes import windll, create_unicode_buffer, c_int
            
            # Try to get foreground window (works in interactive session)
            hwnd = windll.user32.GetForegroundWindow()
            
            if hwnd and hwnd != 0:  # Got a valid foreground window (user session)
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
            else:
                # Service mode: Get most recently active process (highest CPU/IO usage)
                try:
                    processes = []
                    for proc in psutil.process_iter(['pid', 'name', 'cpu_num', 'create_time']):
                        try:
                            # Skip system processes and services
                            if proc.info['name'].lower() in ['system', 'svchost.exe', 'csrss.exe', 'services.exe', 'wininit.exe']:
                                continue
                            # Skip common system/background processes
                            if any(x in proc.info['name'].lower() for x in ['system', 'winlogon', 'lsass', 'registry']):
                                continue
                            processes.append({
                                'name': proc.info['name'].replace('.exe', ''),
                                'pid': proc.info['pid'],
                                'cpu_num': proc.info['cpu_num'] or 0
                            })
                        except:
                            pass
                    
                    if processes:
                        # Get process with most activity (sorted by CPU)
                        most_active = sorted(processes, key=lambda x: x['cpu_num'], reverse=True)[0]
                        active_app = most_active['name']
                        window_title = f"[Service Mode] {active_app}"
                except Exception as service_err:
                    logger.debug(f"Service mode process detection failed: {service_err}")
                    
    except Exception as e:
        logger.debug(f"Failed to get active window info: {e}")
    return active_app, window_title


def get_installed_software():
    """Get list of installed software from Windows Registry"""
    try:
        import winreg
        software_list = []
        
        # Query both 64-bit and 32-bit registry keys
        registry_paths = [
            r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
            r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'
        ]
        
        for path in registry_paths:
            try:
                registry_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
                for i in range(winreg.QueryInfoKey(registry_key)[0]):
                    try:
                        subkey_name = winreg.EnumKey(registry_key, i)
                        subkey = winreg.OpenKey(registry_key, subkey_name)
                        
                        try:
                            display_name = winreg.QueryValueEx(subkey, 'DisplayName')[0]
                            display_version = winreg.QueryValueEx(subkey, 'DisplayVersion')[0] if 'DisplayVersion' in [winreg.EnumValue(subkey, j)[0] for j in range(winreg.QueryInfoKey(subkey)[1])] else ''
                            
                            if display_name and len(display_name.strip()) > 0:
                                software_list.append({
                                    'name': display_name,
                                    'version': display_version,
                                    'registry_key': subkey_name
                                })
                        except:
                            pass
                        finally:
                            winreg.CloseKey(subkey)
                    except:
                        pass
                
                winreg.CloseKey(registry_key)
            except:
                pass
        
        # Remove duplicates and sort
        unique_software = {s['name']: s for s in software_list}.values()
        software_list = sorted(unique_software, key=lambda x: x['name'])
        
        logger.info(f"Found {len(software_list)} installed software packages")
        return software_list
    except Exception as e:
        logger.error(f"Error getting installed software: {e}")
        return []

def fetch_and_execute_commands():
    """Poll for commands and execute them"""
    hostname = socket.gethostname()
    headers = {
        'X-Agent-Key': AGENT_KEY,
        'X-Hostname': hostname
    }
    
    try:
        resp = requests.get(f"{SERVER_URL}/api/v2/agent/commands", headers=headers, timeout=30)
        if resp.status_code == 200:
            commands = resp.json()
            for cmd in commands:
                command_str = cmd['command']
                params_raw = cmd.get('parameters', '') or ''
                
                # FIX: Only extract 'script' from parameters if it exists
                # Don't append raw JSON parameters to command strings
                if params_raw:
                    try:
                        params_obj = json.loads(params_raw)
                        # If params contain 'script', use it as the actual command
                        if isinstance(params_obj, dict) and 'script' in params_obj:
                            command_str = params_obj['script']
                        # Otherwise, DON'T append parameters to the command
                        # Parameters are metadata, not part of the command string
                    except (json.JSONDecodeError, TypeError):
                        # If params aren't valid JSON, just use the command as-is
                        pass
                    
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
                    resp = requests.post(f"{SERVER_URL}/api/v2/agent/commands/result", headers=headers, json=payload, timeout=30)
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
            
            resp = requests.post(f"{SERVER_URL}/api/v2/agent/metrics", json=payload, timeout=30)
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

