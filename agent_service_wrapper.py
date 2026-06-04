"""
ServerMonitor Agent Windows Service Wrapper
============================================
Provides Windows Service installation for agent persistence and auto-start on system restart.
The agent runs as a service and automatically sends data to the portal.

Usage:
  python agent_service_wrapper.py install <agent_key> <server_url> [--interval 30]
  python agent_service_wrapper.py remove
  python agent_service_wrapper.py start
  python agent_service_wrapper.py stop
"""

import sys
import os
import json
import logging
from pathlib import Path
import subprocess

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("[AGENT_SERVICE]")

# Determine agent service installation paths
BASE_DIR = Path(__file__).parent
AGENT_SCRIPT = BASE_DIR / "agent.py"
SERVICE_NAME = "ServerMonitorAgent"
SERVICE_DISPLAY_NAME = "ServerMonitor Agent Service"
SERVICE_DESCRIPTION = "Monitors system metrics and sends to ServerMonitor portal"

# Service configuration file
AGENT_CONFIG_FILE = BASE_DIR / "agent_config.json"


class AgentServiceManager:
    """Manages Windows Service installation/removal for the agent"""
    
    @staticmethod
    def check_admin():
        """Check if running with administrator privileges"""
        try:
            import ctypes
            return ctypes.windll.shell.IsUserAnAdmin()
        except:
            return False
    
    @staticmethod
    def install_service(agent_key: str, server_url: str, interval: int = 30):
        """Install the agent as a Windows Service"""
        
        if not AgentServiceManager.check_admin():
            logger.error("❌ ERROR: Administrator privileges required to install service")
            logger.error("   Please run Command Prompt or PowerShell as Administrator")
            sys.exit(1)
        
        try:
            # Create agent config
            config = {
                "AGENT_KEY": agent_key,
                "SERVER_URL": server_url,
                "INTERVAL": interval,
                "SERVICE_MODE": True
            }
            
            # Write config file
            with open(AGENT_CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
            logger.info(f"✓ Created config file: {AGENT_CONFIG_FILE}")
            
            # Validate Python is available
            python_exe = sys.executable
            logger.info(f"Using Python: {python_exe}")
            
            logger.info(f"Installing {SERVICE_DISPLAY_NAME} using NSSM...")
            
            # 1. Install service with nssm
            install_cmd = f'nssm install {SERVICE_NAME} "{python_exe}" "{AGENT_SCRIPT}"'
            result = subprocess.run(install_cmd, capture_output=True, text=True, shell=True)
            
            if result.returncode != 0 and "already exists" not in result.stderr and "already exists" not in result.stdout:
                logger.error(f"Failed to create service: {result.stderr or result.stdout}")
                return False
            
            # 2. Configure service parameters using nssm
            subprocess.run(f'nssm set {SERVICE_NAME} AppDirectory "{BASE_DIR}"', capture_output=True, shell=True)
            subprocess.run(f'nssm set {SERVICE_NAME} Description "{SERVICE_DESCRIPTION}"', capture_output=True, shell=True)
            subprocess.run(f'nssm set {SERVICE_NAME} DisplayName "{SERVICE_DISPLAY_NAME}"', capture_output=True, shell=True)
            subprocess.run(f'nssm set {SERVICE_NAME} Start SERVICE_AUTO_START', capture_output=True, shell=True)
            
            # Set stdout and stderr redirection
            stdout_path = BASE_DIR / "service.log"
            stderr_path = BASE_DIR / "service_err.log"
            subprocess.run(f'nssm set {SERVICE_NAME} AppStdout "{stdout_path}"', capture_output=True, shell=True)
            subprocess.run(f'nssm set {SERVICE_NAME} AppStderr "{stderr_path}"', capture_output=True, shell=True)
            
            logger.info(f"✅ Service installed successfully: {SERVICE_DISPLAY_NAME}")
            logger.info(f"   Service Name: {SERVICE_NAME}")
            logger.info(f"   Startup Type: Automatic")
            logger.info(f"   Agent Key: {agent_key[:10]}...")
            logger.info(f"   Server URL: {server_url}")
            logger.info(f"   Interval: {interval}s")
            logger.info("")
            logger.info("Start the service with: net start ServerMonitorAgent")
            return True
                    
        except Exception as e:
            logger.error(f"❌ Installation failed: {e}", exc_info=True)
            return False
    
    @staticmethod
    def remove_service():
        """Remove the Windows Service"""
        
        if not AgentServiceManager.check_admin():
            logger.error("❌ ERROR: Administrator privileges required to remove service")
            sys.exit(1)
        
        try:
            logger.info(f"Removing {SERVICE_DISPLAY_NAME}...")
            
            # Stop service if running
            subprocess.run(f"nssm stop {SERVICE_NAME}", capture_output=True, text=True, shell=True)
            
            # Remove service using nssm (skip confirmation)
            cmd = f"nssm remove {SERVICE_NAME} confirm"
            result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
            return_code = result.returncode
            
            if return_code == 0:
                logger.info(f"✅ Service removed successfully")
                return True
            else:
                logger.error(f"Failed to remove service (error code: {return_code})")
                return False
                
        except Exception as e:
            logger.error(f"❌ Removal failed: {e}")
            return False
    
    @staticmethod
    def start_service():
        """Start the Windows Service"""
        
        if not AgentServiceManager.check_admin():
            logger.error("❌ ERROR: Administrator privileges required")
            sys.exit(1)
        
        try:
            cmd = f"nssm start {SERVICE_NAME}"
            result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
            
            if result.returncode == 0:
                logger.info(f"✅ Service started successfully")
                return True
            else:
                logger.error(f"Failed to start service (error code: {result.returncode})")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to start service: {e}")
            return False
    
    @staticmethod
    def stop_service():
        """Stop the Windows Service"""
        
        if not AgentServiceManager.check_admin():
            logger.error("❌ ERROR: Administrator privileges required")
            sys.exit(1)
        
        try:
            cmd = f"nssm stop {SERVICE_NAME}"
            result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
            
            if result.returncode == 0:
                logger.info(f"✅ Service stopped successfully")
                return True
            else:
                logger.error(f"Failed to stop service (error code: {result.returncode})")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to stop service: {e}")
            return False
    
    @staticmethod
    def status():
        """Check service status"""
        try:
            cmd = f"nssm status {SERVICE_NAME}"
            result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
            
            status_out = result.stdout.strip()
            if "SERVICE_RUNNING" in status_out:
                logger.info(f"✓ Service Status: RUNNING")
            elif "SERVICE_STOPPED" in status_out:
                logger.info(f"✓ Service Status: STOPPED")
            else:
                logger.info(f"✓ Service Status: {status_out or 'UNKNOWN'}")
            
            print(result.stdout)
            
        except Exception as e:
            logger.error(f"Failed to check status: {e}")


def main():
    """CLI entry point"""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "install":
        if len(sys.argv) < 4:
            print("Usage: python agent_service_wrapper.py install <agent_key> <server_url> [--interval 30]")
            sys.exit(1)
        
        agent_key = sys.argv[2]
        server_url = sys.argv[3]
        interval = 30
        
        if "--interval" in sys.argv:
            idx = sys.argv.index("--interval")
            if idx + 1 < len(sys.argv):
                interval = int(sys.argv[idx + 1])
        
        AgentServiceManager.install_service(agent_key, server_url, interval)
    
    elif command == "remove":
        AgentServiceManager.remove_service()
    
    elif command == "start":
        AgentServiceManager.start_service()
    
    elif command == "stop":
        AgentServiceManager.stop_service()
    
    elif command == "status":
        AgentServiceManager.status()
    
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
